// Progressive enhancement for dev project pages. The changelog is native
// <details>, so everything here is optional: with JS off the history still
// folds, prints and deep-links.

function setupChangelog(root) {

	const releases = Array.from(root.querySelectorAll('.changelog__release > details'));
	if (!releases.length) return;

	const toggle = root.querySelector('.changelog__toggle-all');
	if (toggle) {

		toggle.hidden = false;
		toggle.addEventListener('click', () => {

			const expand = toggle.dataset.expanded !== 'true';
			releases.forEach((details) => {
				details.open = expand;
			});
			toggle.dataset.expanded = String(expand);
			toggle.textContent = expand ? toggle.dataset.collapseLabel : toggle.dataset.expandLabel;

		});

	}

	// Opening a release should be linkable. Compare against the ids we rendered
	// rather than querying with the raw fragment, so a crafted hash can never
	// become a selector.
	const openFromHash = () => {

		const wanted = window.location.hash.replace(/^#/, '');
		if (!wanted) return;
		const target = releases.find((details) => details.id === wanted);
		if (!target) return;
		target.open = true;
		target.scrollIntoView({ block: 'start', behavior: 'smooth' });

	};

	window.addEventListener('hashchange', openFromHash);
	openFromHash();

}

function init() {

	const changelog = document.querySelector('.devproject__changelog');
	if (changelog) setupChangelog(changelog);

}

if (document.readyState === 'loading') {

	document.addEventListener('DOMContentLoaded', init);

} else {

	init();

}
