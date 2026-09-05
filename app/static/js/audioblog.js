// Audio blog player: highlights the section being narrated, seeks on click,
// and supports chapter permalinks.
//
// The page itself is the transcript, so everything here is an enhancement over
// readable HTML. If the cue track is missing or malformed, nothing is shown and
// the article still reads.

const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const MANUAL_SCROLL_GRACE_MS = 4000;

function readCueTrack() {

	const node = document.getElementById('devcast-cue-track');
	if (!node) return null;
	try {

		const track = JSON.parse(node.textContent);
		return Array.isArray(track?.cues) && track.cues.length ? track : null;

	} catch {

		return null;

	}

}

function formatTime( seconds ) {

	if ( ! Number.isFinite( seconds ) ) return '0:00';
	const total = Math.max( 0, Math.floor( seconds ) );
	const mins = Math.floor( total / 60 );
	return `${ mins }:${ String( total % 60 ).padStart( 2, '0' ) }`;

}

function activeCueIndex( cues, time ) {

	let low = 0;
	let high = cues.length - 1;
	let found = -1;
	while ( low <= high ) {

		const mid = ( low + high ) >> 1;
		if ( cues[ mid ].start <= time ) {

			found = mid;
			low = mid + 1;

		} else {

			high = mid - 1;

		}

	}
	if ( found < 0 ) return -1;
	const end = cues[ found ].end;
	return end != null && time > end ? -1 : found;

}

function start() {

	const track = readCueTrack();
	const root = document.querySelector( '[data-audioblog]' );
	if ( ! track || ! root ) return;

	const audio = root.querySelector( '.audioplayer__audio' );
	const playBtn = root.querySelector( '.audioplayer__play' );
	const prevBtn = root.querySelector( '.audioplayer__prev' );
	const nextBtn = root.querySelector( '.audioplayer__next' );
	const seek = root.querySelector( '.audioplayer__seek' );
	const atLabel = root.querySelector( '.audioplayer__at' );
	const totalLabel = root.querySelector( '.audioplayer__total' );
	const speed = root.querySelector( '.audioplayer__speed select' );
	const follow = root.querySelector( '.audioplayer__follow input' );

	// Only cues whose section is actually on the page can ever be highlighted.
	const cues = track.cues
		.map( ( cue ) => ( { ...cue, el: document.querySelector( `[data-cue-id="${ CSS.escape( cue.id ) }"]` ) } ) )
		.filter( ( cue ) => cue.el )
		.sort( ( a, b ) => a.start - b.start );
	if ( ! cues.length ) return;

	root.hidden = false;

	const duration = () => ( Number.isFinite( audio.duration ) ? audio.duration : track.audio.duration || 0 );
	const storageKey = `devcast:${ location.pathname }`;
	let current = -1;
	let lastManualScroll = 0;

	function setActive( index ) {

		if ( index === current ) return;
		if ( current >= 0 ) {

			cues[ current ].el.classList.remove( 'is-narrating' );
			cues[ current ].el.removeAttribute( 'aria-current' );

		}
		current = index;
		if ( current < 0 ) return;

		const el = cues[ current ].el;
		el.classList.add( 'is-narrating' );
		el.setAttribute( 'aria-current', 'true' );

		const followWanted = follow.checked && ! REDUCED_MOTION;
		const recentlyScrolled = Date.now() - lastManualScroll < MANUAL_SCROLL_GRACE_MS;
		if ( followWanted && ! recentlyScrolled ) {

			el.scrollIntoView( { block: 'center', behavior: 'smooth' } );

		}

	}

	function seekTo( seconds, { play = false, index = null } = {} ) {

		const target = Math.max( 0, seconds );

		// Highlight straight away. The element may still be fetching metadata,
		// in which case it silently ignores currentTime, and the reader would
		// otherwise get no response to their click at all.
		setActive( index != null ? index : activeCueIndex( cues, target ) );

		const apply = () => {

			audio.currentTime = Math.min( target, duration() || target );

		};

		if ( audio.readyState >= HTMLMediaElement.HAVE_METADATA ) apply();
		else audio.addEventListener( 'loadedmetadata', apply, { once: true } );

		if ( play ) audio.play().catch( () => {} );
		else if ( audio.readyState === HTMLMediaElement.HAVE_NOTHING ) audio.load();

	}

	audio.addEventListener( 'timeupdate', () => {

		setActive( activeCueIndex( cues, audio.currentTime ) );
		atLabel.textContent = formatTime( audio.currentTime );
		const total = duration();
		if ( total ) seek.value = String( Math.round( ( audio.currentTime / total ) * 1000 ) );
		sessionStorage.setItem( storageKey, String( audio.currentTime ) );

	} );

	audio.addEventListener( 'loadedmetadata', () => {

		totalLabel.textContent = formatTime( duration() );

	} );
	totalLabel.textContent = formatTime( track.audio.duration || 0 );

	const syncPlayButton = () => {

		const playing = ! audio.paused;
		playBtn.textContent = playing ? '\u23F8' : '\u25B6';
		playBtn.setAttribute( 'aria-label', playing ? playBtn.dataset.pauseLabel : playBtn.dataset.playLabel );

	};
	audio.addEventListener( 'play', syncPlayButton );
	audio.addEventListener( 'pause', syncPlayButton );

	playBtn.addEventListener( 'click', () => {

		if ( audio.paused ) audio.play().catch( () => {} );
		else audio.pause();

	} );

	prevBtn.addEventListener( 'click', () => seekTo( cues[ Math.max( 0, current - 1 ) ]?.start ?? 0 ) );
	nextBtn.addEventListener( 'click', () => {

		const next = cues[ current + 1 ];
		if ( next ) seekTo( next.start );

	} );

	seek.addEventListener( 'input', () => {

		const total = duration();
		if ( total ) seekTo( ( Number( seek.value ) / 1000 ) * total );

	} );

	speed.addEventListener( 'change', () => {

		audio.playbackRate = Number( speed.value ) || 1;

	} );

	window.addEventListener( 'scroll', () => {

		lastManualScroll = Date.now();

	}, { passive: true } );

	// Click or keyboard on a section jumps the narration there.
	cues.forEach( ( cue, index ) => {

		cue.el.addEventListener( 'click', ( event ) => {

			if ( event.target.closest( 'a, button, input, select, textarea, iframe, video, audio' ) ) return;
			seekTo( cue.start, { play: true, index } );

		} );
		cue.el.addEventListener( 'keydown', ( event ) => {

			if ( event.key !== 'Enter' && event.key !== ' ' ) return;
			if ( event.target !== cue.el ) return;
			event.preventDefault();
			seekTo( cue.start, { play: true, index } );

		} );

	} );

	// An embedded video and the narration must not talk over each other.
	for ( const media of document.querySelectorAll( '.audioentry__sections video' ) ) {

		media.addEventListener( 'play', () => audio.pause() );

	}

	// Chapter permalinks. Resolve against the cue list rather than querying with
	// the raw fragment, so a crafted hash cannot become a selector.
	function primeFromLocation() {

		const params = new URLSearchParams( location.search );
		const t = Number( params.get( 't' ) );
		if ( Number.isFinite( t ) && t > 0 ) {

			seekTo( t );
			return true;

		}

		const hash = location.hash.replace( /^#/, '' );
		if ( ! hash ) return false;
		const cue = cues.find( ( c ) => `cue-${ c.id }` === hash );
		// An unknown fragment stays a plain anchor: the browser has already
		// scrolled, and a retired cue must not break the page.
		if ( ! cue ) return false;
		seekTo( cue.start );
		return true;

	}

	if ( ! primeFromLocation() ) {

		const resumeAt = Number( sessionStorage.getItem( storageKey ) );
		if ( Number.isFinite( resumeAt ) && resumeAt > 0 ) seekTo( resumeAt );

	}

	window.addEventListener( 'hashchange', primeFromLocation );

	if ( 'mediaSession' in navigator ) {

		navigator.mediaSession.metadata = new MediaMetadata( {
			title: document.title,
			artist: location.hostname,
		} );
		navigator.mediaSession.setActionHandler( 'previoustrack', () => prevBtn.click() );
		navigator.mediaSession.setActionHandler( 'nexttrack', () => nextBtn.click() );

	}

	syncPlayButton();

}

if ( document.readyState === 'loading' ) {

	document.addEventListener( 'DOMContentLoaded', start );

} else {

	start();

}
