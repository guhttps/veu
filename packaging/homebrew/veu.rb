class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/3d/ae/5cb9456d71ffa1df3265e41ff4c2f659bf058f715dd5484606e372fbdb37/veu-0.7.1.tar.gz"
  sha256 "1f159c82bb893d27dbbf334d60e8960fbccfee0dfe47bd5d1f9203a7c737f0b3"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/57/63/fab754f4af8efaa016f8272f10189e4fcc9b5e2a31453ff71bbf9d8389c6/veu-0.7.1-py3-none-any.whl"
    sha256 "672f7604843aeae50e659dd7d86dbd07329fbb8bb6ea94dde2cd580783fd2ed8"
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
