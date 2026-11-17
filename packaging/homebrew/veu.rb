class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/13/e7/91d6c967c5e2eb30b82c82e0faa35889d5327337c2a83129f6db5c0f6368/veu-0.7.0.tar.gz"
  sha256 "f4f025f3246b5b00f96b3cbbf0291ce956f1c2c26cafb71f15c99268d6eabd83"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/9a/2f/1ac73ea89c1651816aaaa6aa7ffe891cc0c28f71984e9ed7b1518ad0d4d9/veu-0.7.0-py3-none-any.whl"
    sha256 "d5e951a2497e33508ffada384206bb16c29731ca0cc7a83e9fd624adff23cc1f"
  end

  def install
    venv = virtualenv_create(libexec, "python3.13")
    venv.pip_install_and_link resource("veu-wheel")
  end

  test do
    output = pipe_output("#{bin}/veu anonimizar", "CPF 529.982.247-25")
    assert_match "[CPF_1]", output
    refute_match "529.982.247-25", output
  end
end
