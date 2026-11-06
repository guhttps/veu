// Botões de copiar da página de instalação.
(() => {
  "use strict";
  const aviso = document.getElementById("aviso");
  for (const botao of document.querySelectorAll("[data-copiar]")) {
    botao.addEventListener("click", async () => {
      const texto = document.getElementById(botao.dataset.copiar).textContent.trim();
      try {
        await navigator.clipboard.writeText(texto);
      } catch {
        const area = document.createElement("textarea");
        area.value = texto;
        document.body.append(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      aviso.textContent = "Comando copiado. Agora cole na janela e aperte Enter.";
      aviso.classList.add("visivel");
      clearTimeout(botao.tempo);
      botao.tempo = setTimeout(() => aviso.classList.remove("visivel"), 3000);
    });
  }
})();
