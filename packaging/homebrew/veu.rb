class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/0a/e5/2e90d9bf09c813879600085b43c5fc92e3d4bf9f5006dee007b1a9569a63/veu-0.9.1.tar.gz"
  sha256 "881d6a2bd51bb738ca1c3c7a5158e76697a748b0e1dc5a2fcb6741309964b9c8"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/30/1d/c4f8e6d7fdb7fc02b02f713ac04454ef25dfc4d00d7a8baf739429866711/veu-0.9.1-py3-none-any.whl"
    sha256 "8ff736d03cbd60a51fd3c5a44bba969f3ac63e45f81156ca573332fe3d4e3fb5"
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
