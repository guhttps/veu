class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/3e/a4/78bbf7c7c8385fc6ef4635868ab1dc6ba3c3b8bade7835261eea5dc98570/veu-0.6.0.tar.gz"
  sha256 "a06ed7d6ecdc9928d2c5fbb3b402ba29ef63c5d4513ff0dbcf6511d81e1a0875"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/db/44/c7c8d1a4a77fb1b8f9e2065c2f66ab51321b2c7761c542de8f5d7fb044f3/veu-0.6.0-py3-none-any.whl"
    sha256 "1c550331e1471cad4fae0d524e67cba799c3ef2f2fae14377d3c45da3d7f2049"
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
