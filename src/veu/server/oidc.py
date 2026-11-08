"""Login único (OIDC) no gateway: tokens do provedor de identidade da empresa no lugar dos tokens de equipe.

    [oidc]
    emissor = "https://login.microsoftonline.com/<tenant>/v2.0"
    publico = "api://veu"
    claim_equipe = "groups"

    [equipes.atendimento]
    grupos_oidc = ["<id do grupo>"]

O cliente manda o JWT emitido pelo provedor de identidade (Entra ID, Google, Keycloak, Okta...) no X-Veu-Token ou
no Authorization. O Véu confere a assinatura com as chaves públicas do emissor (JWKS, descobertas em
/.well-known/openid-configuration), o emissor, o público e a validade, e escolhe a equipe pelos grupos.
Precisa do cryptography: pip install "veu[oidc]".
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("veu.oidc")
MAX_TOKEN_LENGTH = 16_384
REFRESH_EVERY = 3600.0      # as chaves do emissor mudam de tempos em tempos
MIN_REFRESH_INTERVAL = 60.0  # um token com kid desconhecido não pode forçar uma busca a cada requisição


class OIDCError(Exception):
    """Token recusado. A mensagem diz o motivo, sem repetir o token."""


def _b64decode(part: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    except (binascii.Error, ValueError) as exc:
        raise OIDCError("token malformado") from exc


def _b64int(value: str) -> int:
    return int.from_bytes(_b64decode(value), "big")


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and len(token) <= MAX_TOKEN_LENGTH and token.startswith("ey")


def _http_get_json(url: str) -> dict:
    import httpx

    response = httpx.get(url, timeout=5.0, follow_redirects=False)
    response.raise_for_status()
    return response.json()


class OIDCVerifier:
    """Confere JWTs assinados com RS256/384/512, PS256/384/512 ou ES256/384 (nunca "none" nem HMAC)."""

    def __init__(self, issuer: str, audience: str, jwks: str | dict | None = None, leeway: int = 60,
                 fetch: Callable[[str], dict] = _http_get_json, clock: Callable[[], float] = time.time,
                 background: bool = False):
        """background: busca as chaves numa thread, sem segurar quem chamou verify() (o servidor usa assim, para
        um emissor lento nunca travar as requisições; um token com chave nova recebe 401 até ela chegar)."""
        try:
            from cryptography.hazmat.primitives import hashes
        except ImportError as exc:
            raise RuntimeError('O login por OIDC precisa do cryptography: pip install "veu[oidc]"') from exc
        self._hashes = {"256": hashes.SHA256, "384": hashes.SHA384, "512": hashes.SHA512}
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.leeway = leeway
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, tuple[str, object, str | None]] = {}  # kid -> (kty, chave, alg declarado)
        self._fetched_at: float | None = None
        self._background = background
        self._fetching = False
        self._static: dict | None = None
        self._jwks_uri: str | None = None
        if isinstance(jwks, dict):
            self._static = jwks
        elif jwks and jwks.startswith("https://"):
            self._jwks_uri = jwks
        elif jwks:
            self._static = json.loads(Path(jwks).read_text(encoding="utf-8"))
        if self._static is not None:
            self._load(self._static)

    # Chaves ----------------------------------------------------------------------------------------------------

    def _load(self, document: dict) -> None:
        from cryptography.hazmat.primitives.asymmetric import ec, rsa

        curves = {"P-256": ec.SECP256R1, "P-384": ec.SECP384R1}
        keys: dict[str, tuple[str, object, str | None]] = {}
        for index, jwk in enumerate(document.get("keys") or []):
            if not isinstance(jwk, dict) or jwk.get("use", "sig") != "sig":
                continue
            try:
                if jwk.get("kty") == "RSA":
                    key = rsa.RSAPublicNumbers(_b64int(jwk["e"]), _b64int(jwk["n"])).public_key()
                elif jwk.get("kty") == "EC" and jwk.get("crv") in curves:
                    key = ec.EllipticCurvePublicNumbers(_b64int(jwk["x"]), _b64int(jwk["y"]),
                                                        curves[jwk["crv"]]()).public_key()
                else:
                    continue
            except (KeyError, ValueError, OIDCError):
                continue
            keys[str(jwk.get("kid", f"#{index}"))] = (jwk["kty"], key, jwk.get("alg"))
        self._keys = keys

    def _refresh(self, force: bool = False) -> None:
        if self._static is not None:
            return
        with self._lock:
            now = self._clock()
            if self._fetching:
                return
            if self._fetched_at is not None:
                age = now - self._fetched_at
                # Sem chaves (a última busca falhou), tenta de novo depois de um minuto, mesmo sem ser forçado.
                if age < MIN_REFRESH_INTERVAL or (not force and self._keys and age < REFRESH_EVERY):
                    return
            self._fetched_at = now
            if self._background:
                self._fetching = True
                threading.Thread(target=self._download_in_background, name="veu-oidc", daemon=True).start()
                return
            self._download()

    def _download_in_background(self) -> None:
        try:
            self._download()
        except OIDCError as exc:
            logger.warning("OIDC: %s", exc)
        finally:
            with self._lock:
                self._fetching = False

    def prefetch(self) -> None:
        """Busca as chaves agora (no início do servidor), sem esperar o primeiro token."""
        if self._static is None:
            with self._lock:
                self._fetched_at = self._clock()
                self._download()

    def _download(self) -> None:
        """Descoberta e JWKS. Quem chama segura a trava ou está na thread de busca."""
        try:
            if self._jwks_uri is None:
                discovery = self._fetch(self.issuer + "/.well-known/openid-configuration")
                if str(discovery.get("issuer", "")).rstrip("/") != self.issuer:
                    raise OIDCError("o documento de descoberta é de outro emissor")
                uri = str(discovery.get("jwks_uri", ""))
                if not uri.startswith("https://"):
                    raise OIDCError("o emissor não informou um jwks_uri https")
                self._jwks_uri = uri
            self._load(self._fetch(self._jwks_uri))
        except OIDCError:
            raise
        except Exception as exc:  # noqa: BLE001 - rede, JSON: o token é recusado, o servidor segue
            raise OIDCError(f"não consegui buscar as chaves do emissor ({type(exc).__name__})") from exc

    # Verificação -----------------------------------------------------------------------------------------------

    def verify(self, token: str) -> dict:
        if not looks_like_jwt(token):
            raise OIDCError("não é um JWT")
        header_part, payload_part, signature_part = token.split(".")
        try:
            header = json.loads(_b64decode(header_part))
            claims = json.loads(_b64decode(payload_part))
        except (ValueError, UnicodeDecodeError) as exc:
            raise OIDCError("token malformado") from exc
        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise OIDCError("token malformado")
        algorithm = str(header.get("alg", ""))
        if algorithm[:2] not in ("RS", "PS", "ES") or algorithm[2:] not in self._hashes:
            raise OIDCError(f"algoritmo não aceito: {algorithm or 'nenhum'}")
        self._refresh()
        kid = header.get("kid")
        if kid is not None and str(kid) not in self._keys:
            self._refresh(force=True)  # o emissor pode ter trocado as chaves
        candidates = [self._keys[str(kid)]] if kid is not None and str(kid) in self._keys else (
            [] if kid is not None else list(self._keys.values()))
        signed = f"{header_part}.{payload_part}".encode("ascii")
        signature = _b64decode(signature_part)
        if not self._keys:
            raise OIDCError("as chaves do emissor ainda não foram carregadas; tente de novo em instantes")
        if not any(self._check(algorithm, kty, key, declared, signed, signature)
                   for kty, key, declared in candidates):
            raise OIDCError("assinatura inválida ou chave desconhecida")
        self._check_claims(claims)
        return claims

    def _check(self, algorithm: str, kty: str, key, declared: str | None, signed: bytes, signature: bytes) -> bool:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric import ec, padding
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

        if declared and declared != algorithm:
            return False
        digest = self._hashes[algorithm[2:]]()
        try:
            if algorithm.startswith(("RS", "PS")):
                if kty != "RSA":
                    return False
                pad = padding.PKCS1v15() if algorithm.startswith("RS") else padding.PSS(
                    mgf=padding.MGF1(digest), salt_length=digest.digest_size)
                key.verify(signature, signed, pad, digest)
            else:
                size = {"256": 32, "384": 48}.get(algorithm[2:])
                if kty != "EC" or size is None or len(signature) != 2 * size or key.curve.key_size != size * 8:
                    return False
                der = encode_dss_signature(int.from_bytes(signature[:size], "big"),
                                           int.from_bytes(signature[size:], "big"))
                key.verify(der, signed, ec.ECDSA(digest))
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True

    def _check_claims(self, claims: dict) -> None:
        now = self._clock()
        if str(claims.get("iss", "")).rstrip("/") != self.issuer:
            raise OIDCError("emissor diferente do configurado")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if self.audience not in audiences:
            raise OIDCError("o token não é para o Véu (público diferente)")
        expires = claims.get("exp")
        if not isinstance(expires, (int, float)):
            raise OIDCError("token sem validade (exp)")
        if now > expires + self.leeway:
            raise OIDCError("token expirado")
        not_before = claims.get("nbf")
        if isinstance(not_before, (int, float)) and now + self.leeway < not_before:
            raise OIDCError("token ainda não é válido (nbf)")


def claim_values(claims: dict, name: str) -> set[str]:
    """Valores de uma claim de grupos: lista, texto ou texto separado por espaços (como "scp")."""
    value = claims.get(name)
    if isinstance(value, str):
        return set(value.split())
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()
