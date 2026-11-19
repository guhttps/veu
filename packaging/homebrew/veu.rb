class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/91/1f/f24a6c2255d8c59736b7d71555e0717c2c4622625f699d2d818f083ebbd3/veu-0.8.1.tar.gz"
  sha256 "2c7b085104b668edcdc62545a4b1c1c22ae081fb14c65da85a30d60670d2806a"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/f1/0c/139d99f832feb66ebbe2be3713c5783b988896f045ddda5ecaba0d8f10e2/veu-0.8.1-py3-none-any.whl"
    sha256 "e8802312a92d9235e4361219157550b1e9cda7c0a3940a76cbcb4566c6a71513"
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
