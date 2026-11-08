class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/df/eb/0c8b921ad4036d71ab08a37aec6eafc052b0ba83cd0bd03f622f7900ecca/veu-0.5.2.tar.gz"
  sha256 "9323a79044c47cb68b07db57fcd57ce912fb56490d25785f6ee4b167beadb50c"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/84/59/fed3120ca5e607e87b8e32a6c5de97c54e29b5d97629fbdccd2d21f934fe/veu-0.5.2-py3-none-any.whl"
    sha256 "5c19def69f100af89ba9da204f9b17d5d74d43973ff4a30528563d5bada88166"
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
