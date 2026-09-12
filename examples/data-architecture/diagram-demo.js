/* Animated draw.io diagram — prototype of the §6 engine in docs/devcast-design.md,
 * run against a real export (Data_Architecture-Concept.svg).
 *
 * The one thing this trial exists to prove: **state is a pure function of time**.
 * Everything is built into a single paused GSAP timeline whose playhead is driven
 * from outside, so dragging the scrubber to any point renders the correct picture.
 * In the Wagtail block that driver becomes `audio.currentTime - cue.start`; here
 * it is a range input, which exercises the same path harder.
 */

const VIEW = { w: 2154, h: 914 };          // the export's own viewBox
const MAX_ZOOM = 3.0;                       // never magnify a 2px stroke into a slab
const REDUCED = matchMedia( '(prefers-reduced-motion: reduce)' ).matches;

// draw.io cell ids, named. In the real block these come from Diagram.index and
// the editor picks them from a dropdown — nobody ever types one of these.
const ID = {
	zoneOnramp:   'jL--N1qoml8gLBs9-66e-5',   // "On/Off-Ramp DLZ"
	zoneDomain:   'jL--N1qoml8gLBs9-66e-4',   // "Domain DLZ"

	source:       'eMchM2q8aVYuMzrbJ3zv-30',  // Source System
	onramp:       'eMchM2q8aVYuMzrbJ3zv-22',  // on-ramp data product (hexagon)
	onrampPort:   'eMchM2q8aVYuMzrbJ3zv-28',
	protoIn:      'nFWBtMJlsaCdo008WGRd-20',  // Protocol Transform (file → stream)
	rawStore:     'nFWBtMJlsaCdo008WGRd-21',  // Raw Storage
	dqOnramp:     'fOdsYAS7zbKB1CYuf22Q-10',  // DQ Audit
	rawToCanon:   'nFWBtMJlsaCdo008WGRd-19',  // Raw to Canonical Semantic Transform

	publishPort:  'eMchM2q8aVYuMzrbJ3zv-5',
	publishLabel: 'eMchM2q8aVYuMzrbJ3zv-14',  // "Publish Interface"
	apiPort:      'eMchM2q8aVYuMzrbJ3zv-3',
	apiLabel:     'eMchM2q8aVYuMzrbJ3zv-13',  // "API Interface"

	domain:       'eMchM2q8aVYuMzrbJ3zv-2',   // foundational data product (hexagon)
	canonLoad:    'nFWBtMJlsaCdo008WGRd-1',   // Canonical Load & Policy Enforcement
	mdm:          'nFWBtMJlsaCdo008WGRd-3',   // Master Data Management
	dqDomain:     'nFWBtMJlsaCdo008WGRd-4',   // DQ Audit
	canonServe:   'nFWBtMJlsaCdo008WGRd-2',   // Canonical Data Serve
	rdbms:        'eMchM2q8aVYuMzrbJ3zv-11',
	lakehouse:    'eMchM2q8aVYuMzrbJ3zv-19',

	sqlPort:      'eMchM2q8aVYuMzrbJ3zv-7',
	sqlLabel:     'eMchM2q8aVYuMzrbJ3zv-15',  // "Lakehouse SQL Interface"
	subPort:      '5Dz0dSzOb64fpdrG9RXy-0',
	subLabel:     '5Dz0dSzOb64fpdrG9RXy-2',   // "Subscribe Interface"

	exp:          'eMchM2q8aVYuMzrbJ3zv-32',  // analytics experience product (hexagon)
	canonToExp:   'nFWBtMJlsaCdo008WGRd-16',  // Canonical to Experience (BDL)
	dqExp:        'nFWBtMJlsaCdo008WGRd-17',  // DQ Audit
	mart:         'eMchM2q8aVYuMzrbJ3zv-43',  // Mart
	analyticServe:'nFWBtMJlsaCdo008WGRd-15',  // Analytic Data Serve
	expSqlPort:   'eMchM2q8aVYuMzrbJ3zv-35',
	expSparkPort: '6ybPreQpQYxrGfu7LY2Y-0',
	consumer:     'nFWBtMJlsaCdo008WGRd-32',

	// the return path: an off-ramp product consumes from the same domain product
	// and delivers back out to a source system
	offramp:      'kf_Cia_N1QG3O1UruQM8-11',
	offrampTitle: 'kf_Cia_N1QG3O1UruQM8-12',
	offrampPort:  'kf_Cia_N1QG3O1UruQM8-18',
	canonToRaw:   'kf_Cia_N1QG3O1UruQM8-19',  // Canonical to Raw Semantic Transform
	rawStoreOut:  'kf_Cia_N1QG3O1UruQM8-21',  // Raw Storage
	dqOfframp:    'kf_Cia_N1QG3O1UruQM8-22',  // DQ Audit
	protoOut:     'kf_Cia_N1QG3O1UruQM8-20',  // Protocol Transform (stream → file)

	// connectors (each is a line path + a separately-filled arrowhead path)
	eSourceToOnramp: 'fOdsYAS7zbKB1CYuf22Q-4',
	ePublish:        'eMchM2q8aVYuMzrbJ3zv-24',
	eApiLookup:      '5Dz0dSzOb64fpdrG9RXy-3',
	eSqlToExp:       'eMchM2q8aVYuMzrbJ3zv-41',
	eSubToExp:       '5Dz0dSzOb64fpdrG9RXy-4',
	eExpSql:         'fOdsYAS7zbKB1CYuf22Q-11',
	eExpSpark:       'fOdsYAS7zbKB1CYuf22Q-12',
	eOfframpSub:     'kf_Cia_N1QG3O1UruQM8-23',   // off-ramp → Subscribe Interface
	eOfframpApi:     'kf_Cia_N1QG3O1UruQM8-24',   // off-ramp → API Interface
	eOfframpToSource:'fOdsYAS7zbKB1CYuf22Q-7',    // off-ramp → Source System
};

// The script an editor would build in the admin. `at` is seconds; in the real
// block these come from anchoring each step to a phrase in the narration.
const STEPS = [
	{ at: 0, camera: 'fit',
	  caption: 'Two landing zones: the <b>On/Off-Ramp DLZ</b> on the left, and the <b>Domain DLZ</b> on the right.' },

	{ at: 3.0, camera: [ 'source', 'onrampPort' ], padding: 200,
	  pulse: [ 'source' ],
	  caption: 'Data starts in a <b>source system</b>.' },

	{ at: 6.0, camera: [ 'source', 'onramp' ], padding: 90,
	  draw: [ 'eSourceToOnramp' ], flow: [ 'eSourceToOnramp' ],
	  caption: 'Every source system gets its own <b>on-ramp data product</b>, one per system.' },

	{ at: 10.0, camera: [ 'onramp' ], padding: 60,
	  sequence: [ 'protoIn', 'rawStore', 'dqOnramp', 'rawToCanon' ],
	  caption: 'Inside the on-ramp: <b>protocol transform</b> (file to stream), <b>raw storage</b>, a <b>DQ audit</b>, then <b>raw to canonical</b>.' },

	{ at: 16.0, camera: [ 'onramp', 'publishPort', 'publishLabel' ], padding: 70,
	  draw: [ 'ePublish' ], flow: [ 'ePublish' ], pulse: [ 'publishLabel' ],
	  caption: 'The on-ramp publishes to the <b>streaming publish interface</b> of the domain data product.' },

	{ at: 21.0, camera: [ 'onramp', 'apiPort', 'apiLabel' ], padding: 70,
	  draw: [ 'eApiLookup' ], flow: [ [ 'eApiLookup', { dash: '4 14', speed: 55 } ] ], pulse: [ 'apiLabel' ],
	  caption: 'While publishing it calls the <b>API interface</b> to look things up — primary keys, for instance.' },

	{ at: 26.0, camera: [ 'domain' ], padding: 55,
	  sequence: [ 'canonLoad', 'mdm', 'dqDomain', 'canonServe', 'rdbms', 'lakehouse' ],
	  caption: 'The domain product runs <b>canonical load and policy enforcement</b>, <b>master data management</b>, a <b>DQ audit</b>, then <b>canonical data serve</b>.' },

	{ at: 33.0, camera: [ 'sqlLabel', 'subLabel' ], padding: 150,
	  pulse: [ 'sqlLabel', 'subLabel' ],
	  caption: 'It serves through a <b>Lakehouse SQL interface</b> and a <b>Subscribe interface</b>.' },

	{ at: 37.0, camera: [ 'domain', 'exp' ], padding: 70,
	  draw: [ 'eSqlToExp', 'eSubToExp' ], flow: [ 'eSqlToExp', 'eSubToExp' ],
	  caption: 'An <b>analytics experience data product</b> in the same domain consumes both.' },

	{ at: 42.0, camera: [ 'exp' ], padding: 55,
	  sequence: [ 'canonToExp', 'dqExp', 'mart', 'analyticServe' ],
	  caption: 'It runs <b>canonical to experience</b>, audits, lands a <b>mart</b>, and serves analytics.' },

	{ at: 48.0, camera: [ 'exp', 'consumer' ], padding: 90,
	  draw: [ 'eExpSql', 'eExpSpark' ], flow: [ 'eExpSql', 'eExpSpark' ],
	  caption: 'Consumers reach it over the <b>experience Lakehouse SQL</b> and <b>Spark</b> interfaces.' },

	// The return path. Note the arrows point *at* the interfaces — that is the
	// subscribe/call direction — while the data travels the other way, so the
	// flow on eOfframpSub runs reversed.
	{ at: 53.0, camera: [ 'subLabel', 'offramp' ], padding: 80,
	  draw: [ 'eOfframpSub', 'eOfframpApi' ],
	  flow: [ [ 'eOfframpSub', { dir: -1 } ], [ 'eOfframpApi', { dash: '4 14', speed: 55 } ] ],
	  pulse: [ 'subLabel' ],
	  caption: 'Going the other way, an <b>off-ramp data product</b> subscribes to the same domain product.' },

	{ at: 59.0, camera: [ 'offramp' ], padding: 60,
	  sequence: [ 'canonToRaw', 'rawStoreOut', 'dqOfframp', 'protoOut' ],
	  caption: 'It reverses the journey: <b>canonical to raw</b>, raw storage, a <b>DQ audit</b>, then <b>protocol transform</b> back to file.' },

	{ at: 65.0, camera: [ 'offrampPort', 'source' ], padding: 140,
	  draw: [ 'eOfframpToSource' ], flow: [ 'eOfframpToSource' ], pulse: [ 'source' ],
	  caption: 'And delivers it back out to a <b>source system</b>.' },

	{ at: 70.0, camera: 'fit',
	  caption: 'End to end &mdash; in through the <b>on-ramp</b>, across the <b>domain product</b>, out to <b>analytics</b> and back through the <b>off-ramp</b>.' },
];
const DURATION = 76;

// ---------------------------------------------------------------- lookups
const svg = document.querySelector( '.dgm svg' );
const cam = svg.querySelector( '[data-dgm-camera]' );
const capEl = document.querySelector( '.dgm-caption' );

const missing = new Set();

function cell( key ) {

	const id = ID[ key ] || key;
	const el = typeof id === 'string' ? svg.querySelector( `[data-cell-id="${ CSS.escape( id ) }"]` ) : null;
	if ( ! el ) missing.add( String( key ) );
	return el;

}

/* A draw.io connector is two paths in one cell: the line (fill="none") and the
 * arrowhead (filled). Animating the cell as a whole would swing the head about;
 * they have to be driven separately. */
const lineOf = ( key ) => cell( key )?.querySelector( 'path[fill="none"]' ) || null;
const headOf = ( key ) => [ ...( cell( key )?.querySelectorAll( 'path' ) || [] ) ]
	.find( ( p ) => p.getAttribute( 'fill' ) && p.getAttribute( 'fill' ) !== 'none' );

/* Only real geometry counts towards a bounding box.
 *
 * getBBox() on a draw.io cell is useless on its own: every label is a
 * <foreignObject width="100%" height="100%">, and 100% resolves against the
 * *viewport*, so any cell carrying a label reports a box the size of the whole
 * diagram. Framing on that silently zooms every camera step back out to "fit".
 * Measuring the drawn shapes instead sidesteps it. */
const GEOMETRY = 'path,rect,ellipse,circle,polygon,polyline,line';

function shapesOf( el ) {

	const out = [ ...el.querySelectorAll( GEOMETRY ) ].filter( ( n ) => ! n.closest( 'foreignObject' ) );
	return out.length ? out : [ el ];

}

/* Bounding box of `el` expressed in the camera group's own coordinates. Both
 * CTMs include the camera transform, so it cancels and this stays correct
 * whatever the camera is currently doing. */
function bboxInCamera( el ) {

	const pt = svg.createSVGPoint();
	const inv = cam.getScreenCTM().inverse();
	let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;

	for ( const node of shapesOf( el ) ) {

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
	if ( ! Number.isFinite( x0 ) ) return null;
	return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };

}

/* Camera steps name shapes, never coordinates — so the framing survives the
 * diagram being edited, and is recomputed rather than stored. */
function frame( targets, padding = 60 ) {

	if ( targets === 'fit' ) return { x: 0, y: 0, scale: 1 };

	let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
	for ( const key of targets ) {

		const el = cell( key );
		if ( ! el ) continue;
		const b = bboxInCamera( el );
		if ( ! b ) continue;
		x0 = Math.min( x0, b.x ); y0 = Math.min( y0, b.y );
		x1 = Math.max( x1, b.x + b.w ); y1 = Math.max( y1, b.y + b.h );

	}
	if ( ! Number.isFinite( x0 ) ) return { x: 0, y: 0, scale: 1 };

	const w = x1 - x0 + padding * 2;
	const h = y1 - y0 + padding * 2;
	const s = Math.min( VIEW.w / w, VIEW.h / h, MAX_ZOOM );
	return {
		scale: s,
		x: VIEW.w / 2 - s * ( x0 + ( x1 - x0 ) / 2 ),
		y: VIEW.h / 2 - s * ( y0 + ( y1 - y0 ) / 2 ),
	};

}

// ---------------------------------------------------------------- flow overlays
/* Flow is NOT a timeline tween. An infinitely repeating tween has infinite
 * duration, which would make the timeline unseekable — the exact property this
 * trial is meant to preserve. Instead each flow is a cloned path whose dash
 * offset is computed from the playhead, so it is correct at any t and free to
 * scrub. */
const flows = [];

function addFlow( key, opts = {} ) {

	const line = lineOf( key );
	if ( ! line ) return;
	const overlay = line.cloneNode( false );
	overlay.removeAttribute( 'style' );          // drop draw.io's light-dark() stroke
	overlay.setAttribute( 'stroke', opts.colour || '#ff7a18' );
	overlay.setAttribute( 'stroke-width', opts.width || 3.5 );
	overlay.setAttribute( 'stroke-linecap', 'round' );
	overlay.setAttribute( 'fill', 'none' );
	overlay.setAttribute( 'pointer-events', 'none' );
	overlay.style.strokeDasharray = opts.dash || '16 26';
	overlay.style.opacity = '0';
	line.parentNode.insertBefore( overlay, line.nextSibling );
	flows.push( { el: overlay, from: opts.from || 0, speed: opts.speed || 70, dir: opts.dir || 1 } );

}

function renderFlows( t ) {

	for ( const f of flows ) {

		const live = t >= f.from;
		f.el.style.opacity = live ? String( Math.min( 1, ( t - f.from ) / 0.6 ) ) : '0';
		// negative offset marches the dashes along the path's own direction;
		// dir:-1 sends them back up it, for data arriving over a subscribe
		if ( live ) f.el.style.strokeDashoffset = String( - ( t - f.from ) * f.speed * f.dir );

	}

}

// ---------------------------------------------------------------- build
function build() {

	gsap.set( cam, { transformOrigin: '0px 0px' } );

	const tl = gsap.timeline( { paused: true } );
	tl.to( {}, { duration: DURATION }, 0 );   // dummy tween, pins the timeline's length

	for ( const step of STEPS ) {

		if ( step.camera ) {

			const to = frame( step.camera, step.padding );
			if ( step.at === 0 || REDUCED ) tl.set( cam, to, step.at );
			else tl.to( cam, { ...to, duration: 1.7, ease: 'power2.inOut' }, step.at );

		}

		for ( const key of step.draw || [] ) {

			const line = lineOf( key );
			if ( ! line ) continue;
			const head = headOf( key );
			const len = line.getTotalLength();
			if ( ! len ) {                       // unrendered path: degrade to a fade

				tl.fromTo( line, { opacity: 0 }, { opacity: 1, duration: 0.9 }, step.at );

			} else {

				tl.fromTo( line,
					{ strokeDasharray: len, strokeDashoffset: len },
					{ strokeDashoffset: 0, duration: 1.4, ease: 'power1.inOut' }, step.at );

			}
			// the head is a separate shape and would otherwise sit waiting at the
			// far end while the line is still on its way
			if ( head ) tl.fromTo( head, { opacity: 0 }, { opacity: 1, duration: 0.3 }, step.at + 1.15 );

		}

		for ( const entry of step.flow || [] ) {

			const [ key, opts ] = Array.isArray( entry ) ? entry : [ entry, {} ];
			addFlow( key, { ...opts, from: step.at + 1.2 } );

		}

		for ( const key of step.pulse || [] ) {

			const el = cell( key );
			if ( el ) tl.to( el, {
				scale: 1.08, transformOrigin: '50% 50%', duration: 0.35,
				yoyo: true, repeat: 1, ease: 'sine.inOut',
			}, step.at + 0.6 );

		}

		// walk the internals of a product, one beat each
		( step.sequence || [] ).forEach( ( key, i ) => {

			const el = cell( key );
			if ( ! el ) return;
			const at = step.at + 0.8 + i * 0.85;
			tl.fromTo( el, { opacity: 0.25 }, { opacity: 1, duration: 0.5 }, at );
			tl.to( el, {
				scale: 1.05, transformOrigin: '50% 50%', duration: 0.3,
				yoyo: true, repeat: 1, ease: 'sine.inOut',
			}, at );

		} );

	}

	return tl;

}

// ---------------------------------------------------------------- drive
function main() {

	const tl = build();

	const playBtn = document.querySelector( '[data-play]' );
	const seek = document.querySelector( '[data-seek]' );
	const clock = document.querySelector( '[data-clock]' );
	const chips = [ ...document.querySelectorAll( '[data-step]' ) ];

	let playing = false;
	let last = 0;
	let t = 0;

	function captionFor( time ) {

		let cur = STEPS[ 0 ];
		for ( const s of STEPS ) if ( s.at <= time ) cur = s;
		return cur;

	}

	function render( time ) {

		t = Math.max( 0, Math.min( DURATION, time ) );
		tl.seek( t );                    // everything GSAP owns
		renderFlows( t );                // everything derived from the playhead
		const step = captionFor( t );
		if ( capEl.dataset.at !== String( step.at ) ) {

			capEl.dataset.at = String( step.at );
			capEl.innerHTML = step.caption;

		}
		seek.value = String( Math.round( ( t / DURATION ) * 1000 ) );
		clock.textContent = `${ t.toFixed( 1 ) }s / ${ DURATION }s`;
		for ( const c of chips ) c.setAttribute( 'aria-current', String( Number( c.dataset.step ) === step.at ) );

	}

	function tick( now ) {

		if ( playing ) {

			render( t + ( now - last ) / 1000 );
			if ( t >= DURATION ) setPlaying( false );

		}
		last = now;
		requestAnimationFrame( tick );

	}

	function setPlaying( on ) {

		playing = on && ! REDUCED;
		playBtn.textContent = playing ? 'Pause' : 'Play';

	}

	playBtn.addEventListener( 'click', () => {

		if ( t >= DURATION ) render( 0 );
		setPlaying( ! playing );

	} );
	seek.addEventListener( 'input', () => {

		setPlaying( false );
		render( ( Number( seek.value ) / 1000 ) * DURATION );

	} );
	for ( const c of chips ) c.addEventListener( 'click', () => {

		setPlaying( false );
		render( Number( c.dataset.step ) );

	} );

	if ( REDUCED ) {

		// Everything present, nothing moving, camera left on the whole diagram.
		render( DURATION );
		gsap.set( cam, frame( 'fit' ) );
		playBtn.disabled = true;
		playBtn.textContent = 'Reduced motion';

	} else {

		// ?t=<seconds> lands on a given moment, the way audioblog.js already does
		// for narration. Also how the screenshots in the write-up were taken.
		const t0 = Number( new URLSearchParams( location.search ).get( 't' ) );
		render( Number.isFinite( t0 ) && t0 > 0 ? t0 : 0 );

	}

	requestAnimationFrame( tick );

	// Bounding boxes are measured in CSS pixels via getScreenCTM, so a resize
	// invalidates every camera target. Rebuild and land on the same playhead.
	let resizeTimer;
	addEventListener( 'resize', () => {

		clearTimeout( resizeTimer );
		resizeTimer = setTimeout( () => render( t ), 200 );

	} );

	if ( missing.size ) console.warn( 'diagram: steps target missing cells:', [ ...missing ] );
	window.__dgm = { tl, render, frame, STEPS, missing };   // for screenshots and poking about

}

function boot() {

	try {

		main();

	} catch ( err ) {

		// The SVG ships in its final state, so a dead engine degrades to a
		// static diagram rather than a blank one.
		console.error( err );
		capEl.innerHTML = `<span style="color:#ff9d9d">Animation engine failed: ${ err.message }</span>`;
		document.querySelector( '[data-play]' ).disabled = true;

	}

}

if ( document.readyState === 'loading' ) addEventListener( 'DOMContentLoaded', boot );
else boot();
