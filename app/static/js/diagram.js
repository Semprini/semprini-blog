// Animated draw.io diagrams. One paused GSAP timeline per figure, with its
// playhead driven from outside: by narration time where the page has it, by the
// figure's own controls otherwise. State is a pure function of the playhead, so
// seeking anywhere - a scrub, a chapter permalink, a narration jump - renders
// the right picture.
//
// The SVG ships in its FINAL state and this sets the "from" states, so a reader
// with no JS, a failed load, or reduced motion still gets the whole diagram.
// See §6 of docs/devcast-design.md; the findings that shaped it are in
// examples/data-architecture/FINDINGS.md.

// Vendored beside this module rather than pulled from a CDN, matching how
// three.js is served. import.meta.url resolves it correctly whether static is
// served from Django or from the S3 bucket.
const GSAP_URL = new URL( 'gsap.min.js', import.meta.url ).href;
const REDUCED = matchMedia( '(prefers-reduced-motion: reduce)' ).matches;
const MAX_ZOOM = 3.0;          // never magnify a 2px stroke into a slab
const GEOMETRY = 'path,rect,ellipse,circle,polygon,polyline,line';

let gsapPromise = null;

// The narration track audioblog.js publishes. Read directly rather than passed
// in, so neither module has to import the other.
function cueTrack() {

	const node = document.getElementById( 'devcast-cue-track' );
	if ( ! node ) return null;
	try { return JSON.parse( node.textContent ); } catch { return null; }

}

const normalise = ( s ) => String( s || '' ).toLowerCase()
	.replace( /[^a-z0-9]+/g, ' ' ).trim().split( ' ' ).filter( Boolean );

// First index at or after `from` where `hay` contains all of `needle` in order.
function findRun( hay, needle, from ) {

	if ( ! needle.length ) return - 1;
	const n = Math.min( needle.length, 4 );      // a few words is enough to place it
	for ( let i = from; i <= hay.length - n; i ++ ) {

		let ok = true;
		for ( let j = 0; j < n; j ++ ) if ( hay[ i + j ] !== needle[ j ] ) { ok = false; break; }
		if ( ok ) return i;

	}
	return - 1;

}

// Only fetched when a page actually has an animated diagram on it.
function loadGsap() {

	if ( window.gsap ) return Promise.resolve( window.gsap );
	if ( ! gsapPromise ) gsapPromise = new Promise( ( resolve, reject ) => {

		const tag = document.createElement( 'script' );
		tag.src = GSAP_URL;
		tag.onload = () => resolve( window.gsap );
		tag.onerror = () => reject( new Error( 'GSAP did not load' ) );
		document.head.appendChild( tag );

	} );
	return gsapPromise;

}

class Diagram {

	constructor( figure, gsap ) {

		this.figure = figure;
		this.gsap = gsap;
		this.svg = figure.querySelector( 'svg' );
		this.cam = this.svg.querySelector( '[data-dgm-camera]' );
		this.caption = figure.querySelector( '.dgm-caption' );

		const json = figure.querySelector( 'script[type="application/json"]' );
		const script = json ? JSON.parse( json.textContent ) : {};
		/* One knob for pace. Halving every `at` alone would not work: the
		 * engine's own durations (a draw, a camera move, a sequence stagger)
		 * are fixed, so the steps would start overlapping. `speed` divides
		 * both, keeping the shape of the animation and only changing its
		 * tempo. */
		this.speed = Number( script.speed ) > 0 ? Number( script.speed ) : 1;
		this.steps = ( script.steps || [] ).map(
			( s ) => ( { ...s, at: ( s.at || 0 ) / this.speed } ) );
		this.duration = ( script.duration || 0 ) / this.speed;
		// A looping diagram is decoration rather than narration: it plays itself
		// while on screen and has nothing to say, so it carries no captions.
		this.loop = Boolean( script.loop );
		// A script may name targets by alias; the diagram knows them by cell id.
		this.aliases = script.targets || {};
		this.view = { w: this.svg.viewBox.baseVal.width, h: this.svg.viewBox.baseVal.height };

		this.flows = [];
		this.missing = new Set();
		this.t = 0;

	}

	cell( key ) {

		const id = this.aliases[ key ] || key;
		const el = typeof id === 'string'
			? this.svg.querySelector( `[data-cell-id="${ CSS.escape( id ) }"]` ) : null;
		if ( ! el ) this.missing.add( String( key ) );
		return el;

	}

	// A draw.io connector is two paths in one cell: the line (fill="none") and a
	// separately filled arrowhead. Driving the cell as a whole swings the head about.
	line( key ) { return this.cell( key )?.querySelector( 'path[fill="none"]' ) || null; }

	head( key ) {

		return [ ...( this.cell( key )?.querySelectorAll( 'path' ) || [] ) ]
			.find( ( p ) => p.getAttribute( 'fill' ) && p.getAttribute( 'fill' ) !== 'none' );

	}

	/* getBBox() on a draw.io cell is useless on its own: every label is a
	 * <foreignObject width="100%" height="100%">, and 100% resolves against the
	 * viewport, so any labelled cell reports a box the size of the whole diagram
	 * and every camera step silently falls back to "fit". Measure the drawn
	 * shapes instead. */
	bbox( el ) {

		const nodes = [ ...el.querySelectorAll( GEOMETRY ) ]
			.filter( ( n ) => ! n.closest( 'foreignObject' ) );
		const pt = this.svg.createSVGPoint();
		const inv = this.cam.getScreenCTM().inverse();
		let x0 = Infinity, y0 = Infinity, x1 = - Infinity, y1 = - Infinity;

		for ( const node of ( nodes.length ? nodes : [ el ] ) ) {

			let b;
			try { b = node.getBBox(); } catch { continue; }
			if ( ! b || ( ! b.width && ! b.height ) ) continue;
			const m = inv.multiply( node.getScreenCTM() );
			for ( const [ x, y ] of [ [ b.x, b.y ], [ b.x + b.width, b.y ],
				[ b.x, b.y + b.height ], [ b.x + b.width, b.y + b.height ] ] ) {

				pt.x = x; pt.y = y;
				const p = pt.matrixTransform( m );
				x0 = Math.min( x0, p.x ); y0 = Math.min( y0, p.y );
				x1 = Math.max( x1, p.x ); y1 = Math.max( y1, p.y );

			}

		}
		return Number.isFinite( x0 ) ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null;

	}

	// Camera steps name shapes, never coordinates, so the framing survives the
	// diagram being edited and is recomputed rather than stored.
	frame( targets, padding = 60 ) {

		if ( targets === 'fit' || ! targets ) return { x: 0, y: 0, scale: 1 };
		const keys = Array.isArray( targets ) ? targets : [ targets ];
		let x0 = Infinity, y0 = Infinity, x1 = - Infinity, y1 = - Infinity;

		for ( const key of keys ) {

			const el = this.cell( key );
			const b = el && this.bbox( el );
			if ( ! b ) continue;
			x0 = Math.min( x0, b.x ); y0 = Math.min( y0, b.y );
			x1 = Math.max( x1, b.x + b.w ); y1 = Math.max( y1, b.y + b.h );

		}
		if ( ! Number.isFinite( x0 ) ) return { x: 0, y: 0, scale: 1 };

		const s = Math.min(
			this.view.w / ( x1 - x0 + padding * 2 ),
			this.view.h / ( y1 - y0 + padding * 2 ),
			MAX_ZOOM );
		return {
			scale: s,
			x: this.view.w / 2 - s * ( x0 + ( x1 - x0 ) / 2 ),
			y: this.view.h / 2 - s * ( y0 + ( y1 - y0 ) / 2 ),
		};

	}

	/* Flow is deliberately not a timeline tween: an infinitely repeating tween
	 * has infinite duration and would make the timeline unseekable, which is the
	 * one property everything here depends on. Each flow is a cloned path whose
	 * dash offset is computed from the playhead. */
	addFlow( key, opts = {} ) {

		const line = this.line( key );
		if ( ! line ) return;
		const overlay = line.cloneNode( false );
		overlay.removeAttribute( 'style' );        // drop draw.io's light-dark() stroke
		overlay.setAttribute( 'stroke', opts.colour || '#ff7a18' );
		overlay.setAttribute( 'stroke-width', opts.width || 3.5 );
		overlay.setAttribute( 'stroke-linecap', 'round' );
		overlay.setAttribute( 'fill', 'none' );
		overlay.setAttribute( 'pointer-events', 'none' );
		overlay.style.strokeDasharray = opts.dash || '16 26';
		overlay.style.opacity = '0';
		line.parentNode.insertBefore( overlay, line.nextSibling );
		// dir -1 sends the dashes back up the path, for data arriving over a
		// subscribe: the arrow points at the interface, the data travels the other way
		this.flows.push( {
			el: overlay, from: opts.from || 0,
			speed: opts.speed || 70, dir: opts.dir || 1,
		} );

	}

	renderFlows( t ) {

		for ( const f of this.flows ) {

			const live = t >= f.from;
			f.el.style.opacity = live
				? String( Math.min( 1, ( t - f.from ) / ( 0.6 / this.speed ) ) ) : '0';
			if ( live ) f.el.style.strokeDashoffset =
				String( - ( t - f.from ) * f.speed * f.dir * this.speed );

		}

	}

	/* Put each step where its caption is actually spoken.
	 *
	 * The block's narration is the captions themselves (see DiagramBlock in
	 * blocks.py), so every step's words appear in the word timings in order.
	 * Matching against them beats replaying the authored timeline, which was
	 * written against nothing and drifts as soon as the voice or its pace
	 * changes. Falls back to the authored `at` for any step it cannot place. */
	anchorTo( cue, words ) {

		if ( ! cue || ! words || ! words.length ) return false;
		const end = cue.end == null ? Infinity : cue.end;
		const win = words.filter( ( w ) => w[ 0 ] >= cue.start - 0.05 && w[ 0 ] < end );
		if ( ! win.length ) return false;

		/* One spoken word can be several tokens - "on-ramp" is "on" + "ramp" -
		 * and a caption is tokenised the same way, so they only line up if both
		 * sides are flattened. Keeping just the first token silently lost every
		 * caption containing a hyphen. `times` maps each token back to the
		 * start of the word it came from. */
		const spoken = [];
		const times = [];
		for ( const w of win ) {

			for ( const token of normalise( w[ 2 ] ) ) { spoken.push( token ); times.push( w[ 0 ] ); }

		}

		let from = 0;
		let placed = 0;
		for ( const step of this.steps ) {

			const caption = normalise( step.caption );
			if ( ! caption.length ) continue;
			const hit = findRun( spoken, caption, from );
			if ( hit < 0 ) continue;
			step.at = Math.max( 0, times[ hit ] - cue.start );
			from = hit + 1;
			placed ++;

		}
		if ( ! placed ) return false;

		this.steps.sort( ( a, b ) => a.at - b.at );
		this.duration = Math.max( ( end === Infinity ? 0 : end ) - cue.start,
			this.steps[ this.steps.length - 1 ].at + 2 );
		this.anchored = placed;
		return true;

	}

	build() {

		const { gsap } = this;
		gsap.set( this.cam, { transformOrigin: '0px 0px' } );
		const k = this.speed;
		const tl = gsap.timeline( { paused: true } );
		tl.to( {}, { duration: this.duration }, 0 );     // pins the timeline's length

		for ( const step of this.steps ) {

			const at = step.at || 0;

			if ( step.camera ) {

				const to = this.frame( step.camera, step.padding );
				if ( at === 0 || REDUCED ) tl.set( this.cam, to, at );
				else tl.to( this.cam, { ...to, duration: 1.7 / k, ease: 'power2.inOut' }, at );

			}

			for ( const key of step.draw || [] ) {

				const line = this.line( key );
				if ( ! line ) continue;
				const head = this.head( key );
				let len = 0;
				// getTotalLength() returns 0 inside a display:none subtree, which
				// would leave a connector that never draws.
				try { len = line.getTotalLength(); } catch { len = 0; }
				if ( len ) {

					tl.fromTo( line,
						{ strokeDasharray: len, strokeDashoffset: len },
						{ strokeDashoffset: 0, duration: 1.4 / k, ease: 'power1.inOut' }, at );

				} else {

					tl.fromTo( line, { opacity: 0 }, { opacity: 1, duration: 0.9 / k }, at );

				}
				// the head would otherwise sit waiting at the far end while the
				// line is still on its way
				if ( head ) tl.fromTo( head, { opacity: 0 }, { opacity: 1, duration: 0.3 / k }, at + 1.15 / k );

			}

			for ( const entry of step.flow || [] ) {

				const [ key, opts ] = Array.isArray( entry ) ? entry : [ entry, {} ];
				this.addFlow( key, { ...opts, from: at + 1.2 / k } );

			}

			for ( const key of step.pulse || [] ) {

				const el = this.cell( key );
				if ( el ) tl.to( el, {
					scale: 1.08, transformOrigin: '50% 50%', duration: 0.35 / k,
					yoyo: true, repeat: 1, ease: 'sine.inOut',
				}, at + 0.6 / k );

			}

			/* Reveal a group of shapes. Lightly staggered, because a panel that
			 * wipes in reads better than one that pops. */
			( step.appear || [] ).forEach( ( key, i ) => {

				const el = this.cell( key );
				if ( ! el ) return;
				tl.fromTo( el, { opacity: 0 },
					{ opacity: 1, duration: 0.5 / k, ease: 'power1.out' },
					at + ( i * 0.04 ) / k );

			} );

			// walk the internals of a container, one beat each
			( step.sequence || [] ).forEach( ( key, i ) => {

				const el = this.cell( key );
				if ( ! el ) return;
				const beat = at + ( 0.8 + i * 0.85 ) / k;
				tl.fromTo( el, { opacity: 0.25 }, { opacity: 1, duration: 0.5 / k }, beat );
				tl.to( el, {
					scale: 1.05, transformOrigin: '50% 50%', duration: 0.3 / k,
					yoyo: true, repeat: 1, ease: 'sine.inOut',
				}, beat );

			} );

		}

		this.tl = tl;
		if ( this.missing.size ) {

			// A step naming a shape a re-export removed is a content bug, not a
			// reason to stop. The admin surfaces the same list.
			console.warn( 'diagram: steps target missing cells:', [ ...this.missing ] );

		}
		return tl;

	}

	render( time ) {

		this.t = Math.max( 0, Math.min( this.duration, time ) );
		this.tl.seek( this.t );
		this.renderFlows( this.t );

		let step = this.steps[ 0 ];
		for ( const s of this.steps ) if ( ( s.at || 0 ) <= this.t ) step = s;
		if ( this.caption && step && this.caption.dataset.at !== String( step.at ) ) {

			this.caption.dataset.at = String( step.at );
			this.caption.textContent = step.caption || '';

		}
		this.figure.dispatchEvent( new CustomEvent( 'dgm:time', { detail: { time: this.t } } ) );

	}

}

function wire( diagram ) {

	const figure = diagram.figure;
	const playBtn = figure.querySelector( '[data-dgm-play]' );
	const seek = figure.querySelector( '[data-dgm-seek]' );
	const clock = figure.querySelector( '[data-dgm-clock]' );

	const paint = () => {

		if ( seek ) seek.value = String( Math.round( ( diagram.t / diagram.duration ) * 1000 ) );
		if ( clock ) clock.textContent = `${ diagram.t.toFixed( 1 ) }s`;

	};
	figure.addEventListener( 'dgm:time', paint );

	if ( REDUCED ) {

		// Everything present, nothing moving, camera left on the whole diagram.
		diagram.render( diagram.duration );
		diagram.gsap.set( diagram.cam, diagram.frame( 'fit' ) );
		if ( playBtn ) { playBtn.disabled = true; playBtn.hidden = true; }
		if ( seek ) seek.disabled = true;
		return;

	}

	let playing = false;
	let last = performance.now();

	function tick( now ) {

		if ( playing ) {

			const next = diagram.t + ( now - last ) / 1000;
			if ( next < diagram.duration ) diagram.render( next );
			else if ( diagram.loop ) diagram.render( next - diagram.duration );
			else { diagram.render( diagram.duration ); setPlaying( false ); }

		}
		last = now;
		requestAnimationFrame( tick );

	}

	function setPlaying( on ) {

		playing = on;
		if ( playBtn ) playBtn.textContent = on ? 'Pause' : 'Play';

	}

	playBtn?.addEventListener( 'click', () => {

		if ( diagram.t >= diagram.duration ) diagram.render( 0 );
		setPlaying( ! playing );

	} );
	seek?.addEventListener( 'input', () => {

		setPlaying( false );
		diagram.render( ( Number( seek.value ) / 1000 ) * diagram.duration );

	} );

	// Where the page is narrated, the narration owns the playhead.
	if ( diagram.cue ) {

		document.addEventListener( 'devcast:time', ( event ) => {

			setPlaying( false );
			diagram.render( event.detail.time - diagram.cue.start );

		} );
		// Two things driving one playhead would fight; the audio wins.
		if ( playBtn ) playBtn.hidden = true;
		figure.classList.add( 'dgm--narrated' );

	}

	diagram.render( 0 );
	requestAnimationFrame( tick );

	if ( diagram.loop && ! diagram.cue ) {

		// Autoplay, but never off-screen: an animation nobody is looking at is
		// just battery. Also lets the reader pause it.
		const io = new IntersectionObserver(
			( entries ) => setPlaying( entries[ 0 ].isIntersecting ),
			{ threshold: 0.25 } );
		io.observe( figure );

	}

	let resizeTimer;
	addEventListener( 'resize', () => {

		// Camera targets are measured in rendered pixels, so a resize invalidates
		// every one of them. Rebuild and land on the same playhead.
		clearTimeout( resizeTimer );
		resizeTimer = setTimeout( () => {

			diagram.flows.forEach( ( f ) => f.el.remove() );
			diagram.flows = [];
			diagram.build();
			diagram.render( diagram.t );

		}, 200 );

	} );

}

async function start() {

	const figures = [ ...document.querySelectorAll( '[data-dgm]' ) ]
		.filter( ( f ) => f.querySelector( 'script[type="application/json"]' ) && f.querySelector( 'svg' ) );
	if ( ! figures.length ) return;

	let gsap;
	try {

		gsap = await loadGsap();

	} catch ( err ) {

		// The diagrams are already on the page in their final state; without the
		// engine they are simply static pictures.
		console.warn( 'diagram:', err.message );
		for ( const f of figures ) f.querySelector( '.dgm-bar' )?.remove();
		return;

	}

	for ( const figure of figures ) {

		try {

			const diagram = new Diagram( figure, gsap );
			if ( ! diagram.steps.length || ! diagram.cam ) continue;

			// If this figure sits in a narrated section, take the step times
			// from where the narration actually says them.
			const track = cueTrack();
			const cueEl = figure.closest( '[data-cue-id]' );
			const cue = track && cueEl
				? ( track.cues || [] ).find( ( c ) => c.id === cueEl.dataset.cueId )
				: null;
			if ( cue && diagram.anchorTo( cue, track.words ) ) diagram.cue = cue;

			diagram.build();
			wire( diagram );

		} catch ( err ) {

			console.error( 'diagram:', err );
			figure.querySelector( '.dgm-bar' )?.remove();

		}

	}

}

if ( document.readyState === 'loading' ) addEventListener( 'DOMContentLoaded', start );
else start();
