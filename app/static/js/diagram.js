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

const GSAP_URL = 'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js';
const REDUCED = matchMedia( '(prefers-reduced-motion: reduce)' ).matches;
const MAX_ZOOM = 3.0;          // never magnify a 2px stroke into a slab
const GEOMETRY = 'path,rect,ellipse,circle,polygon,polyline,line';

let gsapPromise = null;

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
		this.steps = script.steps || [];
		this.duration = script.duration || 0;
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
			f.el.style.opacity = live ? String( Math.min( 1, ( t - f.from ) / 0.6 ) ) : '0';
			if ( live ) f.el.style.strokeDashoffset = String( - ( t - f.from ) * f.speed * f.dir );

		}

	}

	build() {

		const { gsap } = this;
		gsap.set( this.cam, { transformOrigin: '0px 0px' } );
		const tl = gsap.timeline( { paused: true } );
		tl.to( {}, { duration: this.duration }, 0 );     // pins the timeline's length

		for ( const step of this.steps ) {

			const at = step.at || 0;

			if ( step.camera ) {

				const to = this.frame( step.camera, step.padding );
				if ( at === 0 || REDUCED ) tl.set( this.cam, to, at );
				else tl.to( this.cam, { ...to, duration: 1.7, ease: 'power2.inOut' }, at );

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
						{ strokeDashoffset: 0, duration: 1.4, ease: 'power1.inOut' }, at );

				} else {

					tl.fromTo( line, { opacity: 0 }, { opacity: 1, duration: 0.9 }, at );

				}
				// the head would otherwise sit waiting at the far end while the
				// line is still on its way
				if ( head ) tl.fromTo( head, { opacity: 0 }, { opacity: 1, duration: 0.3 }, at + 1.15 );

			}

			for ( const entry of step.flow || [] ) {

				const [ key, opts ] = Array.isArray( entry ) ? entry : [ entry, {} ];
				this.addFlow( key, { ...opts, from: at + 1.2 } );

			}

			for ( const key of step.pulse || [] ) {

				const el = this.cell( key );
				if ( el ) tl.to( el, {
					scale: 1.08, transformOrigin: '50% 50%', duration: 0.35,
					yoyo: true, repeat: 1, ease: 'sine.inOut',
				}, at + 0.6 );

			}

			// walk the internals of a container, one beat each
			( step.sequence || [] ).forEach( ( key, i ) => {

				const el = this.cell( key );
				if ( ! el ) return;
				const beat = at + 0.8 + i * 0.85;
				tl.fromTo( el, { opacity: 0.25 }, { opacity: 1, duration: 0.5 }, beat );
				tl.to( el, {
					scale: 1.05, transformOrigin: '50% 50%', duration: 0.3,
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

			diagram.render( diagram.t + ( now - last ) / 1000 );
			if ( diagram.t >= diagram.duration ) setPlaying( false );

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

	// Where the page is narrated, the narration owns the playhead: audioblog.js
	// emits devcast:time on every timeupdate and after every seek.
	document.addEventListener( 'devcast:time', ( event ) => {

		const cue = figure.closest( '[data-cue-id]' );
		if ( ! cue ) return;
		setPlaying( false );
		diagram.render( event.detail.time - ( Number( cue.dataset.cueStart ) || 0 ) );

	} );

	diagram.render( 0 );
	requestAnimationFrame( tick );

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
