pkgname=grimaur-git
pkgver=r214.g0689904
pkgrel=1
pkgdesc="Lightweight AUR helper that uses the official AUR git mirror"
arch=('any')
url="https://github.com/mackilanu/grimaur"
_dev_url="https://github.com/h8d13/grimaur3"
_dev_branch="dot-cache"

license=('MIT')
depends=('python' 'git')
provides=('grimaur')
conflicts=('grimaur')
source=("$pkgname::git+$_dev_url.git#branch=$_dev_branch")
sha256sums=('SKIP')

pkgver() {
	cd "${srcdir}/${pkgname}"
	# always use git hash for version
	printf 'r%s.g%s' "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
	cd "${srcdir}/${pkgname}"
	install -Dm755 grimaur "${pkgdir}/usr/bin/grimaur"
	sed -i "s/^__version__ = .*/__version__ = \"${pkgver}\"/" "${pkgdir}/usr/bin/grimaur"
}
