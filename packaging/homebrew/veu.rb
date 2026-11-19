class Veu < Formula
  include Language::Python::Virtualenv

  desc "Esconde dados pessoais e segredos antes de o texto chegar à IA"
  homepage "https://github.com/guhttps/veu"
  url "https://files.pythonhosted.org/packages/a2/f9/d833dff25b39a0752e15b01ad307b5e53e79d4af85d293f8501e823c9b94/veu-0.8.0.tar.gz"
  sha256 "4dc11022f12acd46a1fe9975f0eab82613a5e6366afa0ca2ec0a1817b7c49d98"
  license "MIT"

  depends_on "python@3.13"

  # O núcleo não tem dependências; a roda pronta dispensa compilar o pacote (e o hatchling).
  resource "veu-wheel" do
    url "https://files.pythonhosted.org/packages/ed/3f/662616a5c834d7bd33e8dc023537478b148d1a9ebce12985581cf63dea97/veu-0.8.0-py3-none-any.whl"
    sha256 "1b5de42bf386526fe780df7c70c38bca824d479249a341115ccb37a03e7af290"
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
