class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/32/86/fa270f9185697062fabd4fb9459a887faa7104ba0196a9b11a02655f52b1/veu-0.9.5.tar.gz"
  sha256 "433667bd31c2dac3dba50284e263aa5be21df1832a68b84b2bcd77c45f4554a6"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/8c/57/e961c87bc0d84de24743201226d71d0441ad49311d1aaf57d2011db53967/veu-0.9.5-py3-none-any.whl"
    sha256 "f61e8759ea900ae07259d15933ea367d026f6b42510358193ed607c018617d22"
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
