class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/0c/2f/abe20e42e1c2cf0b9b972d728266a9ce7da252b61f9eac71b0b9ad6dbf70/veu-0.9.0.tar.gz"
  sha256 "9d385d7c38c32e249e51e96c52b3769750b6722bdaaec208b0b0c2a23f2a5888"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/29/6f/8c68ade373a33e3be8091660e532230e682b9fcb5fd76c952ef0d572566f/veu-0.9.0-py3-none-any.whl"
    sha256 "efe6b3d065f7f1bf336a4674cd997f71a2fc18530c1ac8f29d41ea3b98cb218c"
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
