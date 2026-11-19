class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/f2/d6/c6ccd0b9d7ae32fb38a807b0f3d2c040a1dbea4cb170a3b7757d9bf3b9b9/veu-0.7.2.tar.gz"
  sha256 "9d9badeb6c7527f18aef7bb70b3c10c38113bd3681bf0a2dcc8b415820e5eaa2"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/40/6b/3dc528b944aa7fd42a647e95b1c22087a3f3d3a0c1a2b62e737e6f4d5f3f/veu-0.7.2-py3-none-any.whl"
    sha256 "01b23a175898d6e0d2fb238ccd7ad4ca069da10d89930a60ecec6ae17e4275bf"
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
