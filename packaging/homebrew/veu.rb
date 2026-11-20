class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/8c/58/47c70fbc4d7f0aa7900f066222c82b77d0125b6ed4c71ae8647b8b7ce1c9/veu-0.9.3.tar.gz"
  sha256 "071c2e1ea35fd0c093336f314bcba9146b0e2103da7199bd16b74db285fba256"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/46/70/43bed404fd64b57d627bf704a4355c3a92d3e4f56e1c2da95789892ca27f/veu-0.9.3-py3-none-any.whl"
    sha256 "ad2a317e6ca640c8e70627fe1f40c2c900d3d8b1faabb93784c23bc97ea09f74"
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
