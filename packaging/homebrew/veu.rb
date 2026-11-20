class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/64/0d/df3e15b21415cfa9cdb40255feb98338f4699f94f712e57f5754852cea14/veu-0.9.2.tar.gz"
  sha256 "30d7c6d4ec049580b6a746c5e936382622cc6efc4157b46265c2fe3a8a678acb"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/8f/40/0684f52c5f296c9d37a67708ed5ac122b2dd56bc618b2d9e2b8c7d9153c4/veu-0.9.2-py3-none-any.whl"
    sha256 "b5a6265b106b560d6a01958ad574ea562119cd22b3b59e75ed97f7dbdc2d03c6"
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
