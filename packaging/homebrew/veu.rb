class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/7d/d1/11b518fc47a55f388c56dfa18ff2fb8f67aa1737f37c8212d5e49f379cfe/veu-0.9.6.tar.gz"
  sha256 "6fa62f5923ac24c2d2464031e6428f15ffecbb79bc2e7855f4fe2abb96c3c537"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/30/4c/d6e7bcaf58b0468b1e030a86062199a580f4c488c6a02238d5b817bb6659/veu-0.9.6-py3-none-any.whl"
    sha256 "39ce8d9cc0f8e2af0cf7c164e5cc4e12f65e459d6243c25750e4720302394c0e"
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
