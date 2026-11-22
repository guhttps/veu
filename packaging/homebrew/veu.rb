class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/b2/a3/36b20d147a51943b0623274a1109d1c5ef9d85033ccc4fc89bcee761cb14/veu-0.9.4.tar.gz"
  sha256 "2f785818e1293b1a50f94f9a3b5ac5cb1269e7bba3d5acca4467ee14e8020bd5"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/e0/ff/e6ed1845fd0cdd81cc686fbb79b01a39f77591ce16d8440f2f4aa4ed850f/veu-0.9.4-py3-none-any.whl"
    sha256 "33faaa6907bebc831ce3ed103bd3aaa2ff652c75a03c95ef7a7c526d6e1ce197"
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
