// Semprini avatar: skinned GLB with pointer-driven head look-at and IK arm pointing.
// Coordinates (three.js, Y up): character faces +Z (towards the default camera).
// The character's own left/right (bone suffix L/R) are mirrored on screen: the .R
// arm is the one drawn on the left of the canvas.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { CCDIKSolver } from 'three/addons/animation/CCDIKSolver.js';

const container = document.querySelector( '.canvas-container' );
const MODEL_URL = container.dataset.model;
const HOTZONE = container.closest( '.about' ) || container;
// Blog post titles: the main entry list and the sidebar recent/popular lists.
const LINK_SELECTOR = 'h2.post_title a, .post-summary h5 a';

const MAX_VIEW_WIDTH = 320;
const VIEW_ASPECT = 320 / 450;   // portrait: the whole standing figure, wide enough for an extended arm
const HEADER_RESERVE = 138;      // in-flow height the header keeps; the rest overhangs the page
const HEAD_MAX_ANGLE = THREE.MathUtils.degToRad( 38 );
const HEAD_SMOOTH = 6;      // 1/s, larger = snappier
const HEAD_SWITCH_MS = 1400;
const ARM_SMOOTH = 4;
const ARM_REACH = 0.74;     // < upper arm + forearm so the elbow stays bent
const LOOK_PLANE_Z = 1.6;   // plane in front of the face that pointer rays hit
const IDLE_AFTER_MS = 4000;
// The model stands from y = +1.0 (crown) to -2.17 (soles). The distance fits
// the lot with a little room to spare: the toes stand ~0.6 proud of the target
// plane, so perspective magnifies them and a tighter framing clips the feet.
const CAM_TARGET = new THREE.Vector3( - 0.1, - 0.65, 0 );
const CAM_DIST = 4.7;
// Narration companion. On a narrated page the avatar leaves the header and
// stands beside the section being read, walking down the page as the narration
// moves between sections; audioblog.js drives it through pinTo()/unpin().
const PIN_SCALE = 0.8;      // a fifth smaller: it stands beside the text, not over the page
const PIN_OVERLAP = 0.3;    // fraction of its width that laps over the content's right edge
const PIN_SMOOTH = 4;       // 1/s, how fast it walks from one section to the next
const PIN_MARGIN = 12;      // keeps it this far inside the viewport
const PIN_MIN_WIDTH = 720;  // narrower than this the text fills the screen: stay in the header
const REDUCED_MOTION = window.matchMedia( '(prefers-reduced-motion: reduce)' ).matches;
// Presenting. While narration plays the avatar works like a presenter: it looks
// between the section being read and the camera the way a speaker looks between
// their slides and the room, points out each new section as it arrives, and
// talks with its hands in between. A pointer coming close interrupts all of it
// for a few seconds, then it picks the presentation back up.
// Still to come: mouth shapes off the narration audio, and walking between marks.
const PRESENT_NEAR = 90;                       // px around the canvas that counts as "close"
const PRESENT_ATTENTION_MS = [ 2200, 6000 ];   // how long the pointer holds its attention
const PRESENT_COOLDOWN_MS = 4000;              // ... and how long before it can take it again
const GAZE_TEXT_MS = [ 1600, 3400 ];           // a glance at the section being read
const GAZE_CAMERA_MS = [ 1500, 3000 ];         // ... and back to the room
const POINT_HOLD_MS = [ 1200, 1900 ];          // "here is the next bit"
const GESTURE_MS = [ 1400, 2800 ];
const GESTURE_DRIFT = 0.06;                    // a held hand is never quite still

// Where each hand goes, in model space: +X is the character's left, which is
// screen right; +Z is towards the viewer; the shoulders sit at y -0.71, z 0.16
// and the arms reach 0.74. null rests that arm. The .R arm is the one drawn on
// the left, nearest the text, so it does the pointing and .L mostly beats along.
// The view is only as wide as the body, so a hand much past x -0.95 / +0.75 at
// this depth leaves the frame - these all sit inside that.
const GESTURES = [
	{ weight: 3, L: [ 0.26, - 1.00, 0.88 ], R: [ - 0.46, - 1.00, 0.88 ] },   // both hands, talking
	{ weight: 2, L: null, R: [ - 0.92, - 0.98, 0.72 ] },                     // open hand towards the text
	{ weight: 2, L: [ 0.62, - 0.74, 0.80 ], R: null },                       // one hand up, making a point
	{ weight: 2, L: null, R: [ - 0.84, - 0.70, 0.78 ] },                     // the near hand, raised
	{ weight: 1, L: null, R: null },                                         // hands down for a beat
];
// The section can be anywhere on the page, and pointing straight at it would
// throw the paw out of frame; the target is pulled back to the edge of what the
// camera sees, which still reads as pointing that way.
const POINT_LIMIT = { x: - 1.35, yLo: - 1.6, yHi: 0.05 };

let camera, scene, renderer;
let skinned, ikSolver;
let head, headRestQuat;
let torso, torsoRestQuat, torsoRestPos;
const arms = {};            // side -> { ik, upper, hand, restTarget, target, active }
const face = {};            // lids, brows, ears, mouth bones + rest transforms
const tmpQ = new THREE.Quaternion();
const tmpQ2 = new THREE.Quaternion();
const tmpQ3 = new THREE.Quaternion();
const parentQ = new THREE.Quaternion();
const parentQInv = new THREE.Quaternion();
const tmpV = new THREE.Vector3();
const tmpV2 = new THREE.Vector3();
const tmpE = new THREE.Euler();
const lookPlane = new THREE.Plane( new THREE.Vector3( 0, 0, -1 ), LOOK_PLANE_Z );
const raycaster = new THREE.Raycaster();
const pointerNDC = new THREE.Vector2( 0, 0 );
const lookPoint = new THREE.Vector3( 0, -0.2, LOOK_PLANE_Z );  // where the head looks
const lookGoal = new THREE.Vector3().copy( lookPoint );
const cursorPoint = new THREE.Vector3().copy( lookPoint );
const linkPoint = new THREE.Vector3();
let hoverLink = null;
let lookAtCamera = false;
let headSwitchAt = 0;
let pointerInHotzone = false;
let lastPointerTime = 0;
let idleNextChange = 0;
let needsRender = true;
let elapsed = 0;
let pin = null;             // { el, content, avoid } while narration owns where it stands
// Presenter state. `on` is narration playing; presenting() also needs the pin,
// since the behaviour only makes sense standing beside the text it is reading.
const present = {
	on: false,
	gazeCamera: false,
	gazeUntil: 0,
	gesture: GESTURES[ 0 ],
	gestureUntil: 0,
	pointing: false,        // showing where the new section starts
	attentionUntil: 0,      // the pointer came close and took over until here
};
const gazePoint = new THREE.Vector3();
const handPoint = { L: new THREE.Vector3(), R: new THREE.Vector3() };
let pinY = 0;               // eased top of the canvas, in document space
let viewH = 0;              // rendered canvas height, in CSS pixels
const timer = new THREE.Timer();

// --- expression state. Every value is a 0..1 (or signed) intent that the
// face update eases towards, so later features can set them directly.
const LID_OPEN = 0.06;      // lid bone scale.y when the eye is open (patch hides under the brow)
const BREATH_PERIOD = 4.2;
const expr = {
	blink: { L: 0, R: 0 },          // 0 open .. 1 closed (target)
	blinkNow: { L: 0, R: 0 },       // eased
	narrow: 0,                      // squint: partial lid + brows down
	narrowNow: 0,
	browRaise: 0,                   // -1 furrow .. +1 raise
	browRaiseNow: 0,
	ear: { L: { flick: 0, tilt: 0 }, R: { flick: 0, tilt: 0 } },       // target, radians
	earNow: { L: { flick: 0, tilt: 0 }, R: { flick: 0, tilt: 0 } },
	mouthOpen: 0, mouthWide: 0,     // speech: 0..1 each
	mouthOpenNow: 0, mouthWideNow: 0,
};
// Ear expression offsets are bone-local XYZ eulers (radians), matching the Blender
// pose tests: X ~ flick forward/back, Z ~ side tilt.
let nextBlinkAt = 2.0;
let blinkPhase = { L: 0, R: 0 };   // >0 while a blink is in flight (seconds)
let nextEarEventAt = 3.0;
let earEvent = null;               // { side, kind, t0, dur }
let speechAmp = 0;                 // driven by speak(); 0 = silent

init();

// Public hooks. audioblog.js owns where the avatar stands while a page is being
// read aloud; the rest of its behaviour stays pointer-driven.
window.sempriniAvatar = { pinTo, unpin, setPresenting, speak, setExpression };

function init() {

	renderer = new THREE.WebGLRenderer( { antialias: true, alpha: true, stencil: true } );
	renderer.setPixelRatio( window.devicePixelRatio );
	renderer.toneMapping = THREE.ACESFilmicToneMapping;
	container.appendChild( renderer.domElement );

	camera = new THREE.PerspectiveCamera( 45, VIEW_ASPECT, 0.25, 20 );
	camera.position.set( CAM_TARGET.x + 0.3, CAM_TARGET.y, CAM_DIST );
	camera.lookAt( CAM_TARGET );
	layout();

	const pmremGenerator = new THREE.PMREMGenerator( renderer );
	scene = new THREE.Scene();
	scene.environment = pmremGenerator.fromScene( new RoomEnvironment(), 0.04 ).texture;

	new GLTFLoader().load( MODEL_URL, onModelLoaded );

	window.addEventListener( 'pointermove', onPointerMove, { passive: true } );
	window.addEventListener( 'resize', layout );
	window.addEventListener( 'blur', () => { pointerInHotzone = false; hoverLink = null; } );
	document.addEventListener( 'pointerleave', () => { pointerInHotzone = false; hoverLink = null; } );
	document.addEventListener( 'pointerover', onPointerOver, { passive: true } );

	renderer.setAnimationLoop( animate );

}

// True while the avatar is standing beside the narration rather than in the
// header. Checked rather than cached, so widening a narrow window puts it back
// beside the text without waiting for the next section.
function pinned() {

	return pin !== null && window.innerWidth >= PIN_MIN_WIDTH;

}

// The canvas is fixed to the top of the viewport so the avatar stays put while the
// page scrolls; the container keeps its place in the header layout.
function layout() {

	const slot = Math.round( Math.min( MAX_VIEW_WIDTH, Math.max( 180, window.innerWidth * 0.42 ) ) );
	const slotH = Math.round( slot / VIEW_ASPECT );
	// The header keeps its slot whatever the avatar is doing, so narration
	// starting does not reflow the page underneath it.
	container.style.width = `${ slot }px`;
	container.style.height = `${ slotH }px`;
	container.style.marginBottom = `${ Math.min( 0, HEADER_RESERVE - slotH ) }px`;

	const w = pinned() ? Math.round( slot * PIN_SCALE ) : slot;
	viewH = Math.round( w / VIEW_ASPECT );
	renderer.setSize( w, viewH );
	camera.aspect = w / viewH;
	camera.updateProjectionMatrix();

	const canvas = renderer.domElement;
	if ( pinned() ) {

		const right = ( pin.content || pin.el ).getBoundingClientRect().right;
		const x = Math.min( window.innerWidth - w - PIN_MARGIN, right - w * PIN_OVERLAP );
		canvas.style.left = `${ Math.round( Math.max( PIN_MARGIN, x ) ) }px`;

	} else {

		canvas.style.left = `${ Math.round( container.getBoundingClientRect().left ) }px`;
		canvas.style.top = '0px';

	}
	needsRender = true;

}

// Vertical placement while pinned. The goal is in document space, so scrolling
// carries the avatar with its section immediately and only a change of section
// is eased - easing the viewport position instead would leave it lagging behind
// every scroll.
function placePin( dt, snap = false ) {

	if ( ! pinned() ) return;

	const rect = pin.el.getBoundingClientRect();
	const goal = rect.top + window.scrollY + rect.height / 2 - viewH / 2;
	pinY = ( snap || REDUCED_MOTION ) ? goal : ease( pinY, goal, PIN_SMOOTH, dt );

	// The player bar is sticky at the top of the page: stand under it, not across it.
	let floor = PIN_MARGIN;
	if ( pin.avoid ) {

		const bar = pin.avoid.getBoundingClientRect();
		if ( bar.top <= PIN_MARGIN && bar.bottom > 0 ) floor = bar.bottom + PIN_MARGIN;

	}

	const top = Math.min( window.innerHeight - viewH - PIN_MARGIN, Math.max( floor, pinY - window.scrollY ) );
	renderer.domElement.style.top = `${ Math.round( top ) }px`;

}

// Stand beside `el` instead of in the header: `content` is the column whose
// right edge the avatar laps over, `avoid` a sticky bar to stay clear of.
function pinTo( el, { content = null, avoid = null } = {} ) {

	if ( ! el ) { unpin(); return; }
	const arriving = ! pinned();      // coming from the header: appear in place, don't glide down
	const changed = ! pin || pin.el !== el;
	pin = { el, content, avoid };
	layout();
	placePin( 0, arriving );
	if ( changed && present.on ) newSection();

}

function unpin() {

	if ( ! pin ) return;
	pin = null;
	present.on = false;
	layout();

}

// Narration playing or paused. A paused presenter holds still: it keeps its
// place beside the text, but it has stopped talking, so it stops gesturing.
function setPresenting( on ) {

	if ( on === present.on ) return;
	present.on = !! on;
	if ( present.on ) newSection();

}

function presenting() {

	return present.on && pinned() && !! skinned;

}

function rand( range ) {

	return range[ 0 ] + Math.random() * ( range[ 1 ] - range[ 0 ] );

}

// A new section is a beat in the talk: look at it, point out where it starts,
// and only then carry on talking with the hands.
function newSection() {

	const now = performance.now();
	present.pointing = true;
	present.gestureUntil = now + rand( POINT_HOLD_MS );
	present.gazeCamera = false;
	present.gazeUntil = now + rand( GAZE_TEXT_MS );

}

function nextGesture( now ) {

	present.pointing = false;
	const total = GESTURES.reduce( ( sum, g ) => sum + g.weight, 0 );
	const draw = () => {

		let r = Math.random() * total;
		for ( const g of GESTURES ) { r -= g.weight; if ( r <= 0 ) return g; }
		return GESTURES[ 0 ];

	};
	let g = draw();
	if ( g === present.gesture ) g = draw();   // one retry, so it rarely repeats itself
	present.gesture = g;
	present.gestureUntil = now + rand( GESTURE_MS );

}

// Screen point on the section being read, as a world point on the look plane.
// `start` aims at the first line, which is what gets pointed at; otherwise it is
// the middle of however much of the section is actually on screen, which is
// where a presenter's eyes would go.
const sectionRange = document.createRange();
function sectionPoint( out, start ) {

	if ( ! pin || ! pin.el.isConnected ) return null;
	const box = pin.el.getBoundingClientRect();
	if ( start ) {

		sectionRange.selectNodeContents( pin.el );
		const rects = sectionRange.getClientRects();
		const r = rects.length ? rects[ 0 ] : box;
		return screenToWorld( r.left + Math.min( 40, r.width / 2 ), r.top + r.height / 2, out );

	}
	const top = Math.max( box.top, 0 );
	const bottom = Math.min( box.bottom, window.innerHeight );
	return screenToWorld( box.left + box.width * 0.55, ( top + bottom ) / 2, out );

}

// Presenter gaze: between the section and the room, unless the pointer has just
// come close, in which case it has the avatar's attention for a few seconds.
function presentLook( now ) {

	if ( now < present.attentionUntil ) { lookGoal.copy( cursorPoint ); return; }

	if ( now >= present.gazeUntil ) {

		present.gazeCamera = ! present.gazeCamera;
		present.gazeUntil = now + rand( present.gazeCamera ? GAZE_CAMERA_MS : GAZE_TEXT_MS );

	}
	if ( ! present.gazeCamera && sectionPoint( gazePoint, false ) ) lookGoal.copy( gazePoint );
	else lookGoal.copy( camera.position );

}

// Presenter hands. Gesture targets are authored positions rather than
// directions: updateArms aims the arm at the point and extends it to its own
// reach, so a position roughly a reach away lands where it was drawn.
function presentArms( now, out ) {

	// The pointer took over: the nearer arm follows it, as it does in the header.
	if ( now < present.attentionUntil ) {

		out[ lookPoint.x >= 0 ? 'L' : 'R' ] = lookPoint;
		return;

	}

	if ( now >= present.gestureUntil ) nextGesture( now );

	// Pointing out where the section starts, while it is still on screen to point at.
	if ( present.pointing ) {

		if ( sectionPoint( handPoint.R, true ) ) {

			handPoint.R.x = Math.max( handPoint.R.x, POINT_LIMIT.x );
			handPoint.R.y = Math.min( Math.max( handPoint.R.y, POINT_LIMIT.yLo ), POINT_LIMIT.yHi );
			out.R = handPoint.R;
			return;

		}
		nextGesture( now );

	}

	const drift = GESTURE_DRIFT * Math.sin( elapsed * 2 * Math.PI / 1.7 );
	const drift2 = GESTURE_DRIFT * Math.sin( elapsed * 2 * Math.PI / 2.3 );
	for ( const side of [ 'L', 'R' ] ) {

		const at = present.gesture[ side ];
		if ( ! at ) continue;
		const wobble = side === 'L' ? drift : drift2;
		out[ side ] = handPoint[ side ].set( at[ 0 ], at[ 1 ] + wobble, at[ 2 ] + wobble * 0.5 );

	}

}

function onModelLoaded( gltf ) {

	scene.add( gltf.scene );
	// One primitive per material; all share the same skeleton.
	const skinnedMeshes = [];
	gltf.scene.traverse( ( o ) => { if ( o.isSkinnedMesh ) skinnedMeshes.push( o ); } );
	if ( skinnedMeshes.length === 0 ) { needsRender = true; return; }
	skinned = skinnedMeshes[ 0 ];

	// Skinned meshes are frustum-culled by their rest-pose bounds; disable so posed arms never vanish.
	for ( const m of skinnedMeshes ) m.frustumCulled = false;
	setupMouthPortal( skinnedMeshes );

	// GLTFLoader sanitises node names: Blender's "Hand.L" arrives as "HandL".
	const bones = skinned.skeleton.bones;
	const index = ( name ) => bones.findIndex( ( b ) => b.name === name );
	const bone = ( name ) => bones[ index( name ) ];

	head = bone( 'Head' );
	headRestQuat = head.quaternion.clone();
	torso = bone( 'Torso' );
	torsoRestQuat = torso.quaternion.clone();
	torsoRestPos = torso.position.clone();

	// Face bones: Lid/Brow/Mouth were authored pointing straight down, so their
	// local +Y is world down and scale.y extends the patch downwards.
	for ( const side of [ 'L', 'R' ] ) {

		const lid = bone( `Lid${ side }` );
		const brow = bone( `Brow${ side }` );
		const ear = bone( `Ear${ side }` );
		face[ side ] = {
			lid, brow, ear,
			browRestPos: brow.position.clone(),
			earRestQuat: ear.quaternion.clone(),
		};
		lid.scale.y = LID_OPEN;

	}

	face.mouth = bone( 'Mouth' );
	face.mouth.scale.set( 0.4, 0.05, 1 );

	const iks = [];
	for ( const side of [ 'L', 'R' ] ) {

		const ikBone = bone( `IK_Hand${ side }` );
		const hand = bone( `Hand${ side }` );
		const upper = bone( `UpperArm${ side }` );
		const fore = bone( `ForeArm${ side }` );
		const restTarget = hand.getWorldPosition( new THREE.Vector3() );
		const ik = {
			target: index( `IK_Hand${ side }` ),
			effector: index( `Hand${ side }` ),
			links: [ { index: index( `ForeArm${ side }` ) }, { index: index( `UpperArm${ side }` ) } ],
			iteration: 20,
			minAngle: 0.0,
			maxAngle: 0.5,
		};
		arms[ side ] = {
			ik: ikBone,
			chain: ik,
			upper,
			links: [ upper, fore ],
			restQuats: [ upper.quaternion.clone(), fore.quaternion.clone() ],
			restTarget,
			target: restTarget.clone(),
			goal: restTarget.clone(),
			pointing: false,
		};
		iks.push( ik );

	}

	ikSolver = new CCDIKSolver( skinned, iks );
	window.__avatarDebug = {
		arms, head, ikSolver, lookPoint, linkPoint, cursorPoint, camera, scene, renderer, face, expr,
		get inHot() { return pointerInHotzone; },
		get link() { return hoverLink; },
		get lookAtCamera() { return lookAtCamera; },
		present, GESTURES,
		speak, setExpression, pinTo, unpin, setPresenting,
	};
	needsRender = true;

}

// Public hooks for later features (speech, moods). Values are eased in updateFace.
function setExpression( partial ) {

	Object.assign( expr, partial );

}

// Drive the mouth from an amplitude in 0..1 (e.g. from audio analysis); 0 closes it.
function speak( amplitude ) {

	speechAmp = Math.max( 0, Math.min( 1, amplitude ) );

}

// The mouth is a stencil portal: the mask ellipse (scaled by the Mouth bone) is
// drawn invisibly after the body, writing stencil=1 only where it is the nearest
// surface. The cavity then draws through that stencil ignoring the muzzle's
// depth, so the bowl appears recessed into the head; tongue and teeth depth-test
// against the cavity. Anything really in front of the mouth (a paw) still
// occludes it because the mask failed the depth test there.
function setupMouthPortal( meshes ) {

	const byMat = {};
	for ( const m of meshes ) byMat[ m.material.name ] = m;
	const mask = byMat.mouth_mask, cavity = byMat.mouth_cavity;
	if ( ! mask || ! cavity ) return;

	mask.renderOrder = 10;
	Object.assign( mask.material, {
		colorWrite: false, depthWrite: false, side: THREE.DoubleSide,
		stencilWrite: true, stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc,
		stencilZPass: THREE.ReplaceStencilOp, stencilZFail: THREE.KeepStencilOp, stencilFail: THREE.KeepStencilOp,
	} );

	cavity.renderOrder = 11;
	Object.assign( cavity.material, {
		side: THREE.DoubleSide, depthFunc: THREE.AlwaysDepth, depthWrite: true,
		stencilWrite: true, stencilRef: 1, stencilFunc: THREE.EqualStencilFunc,
		stencilZPass: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, stencilFail: THREE.KeepStencilOp,
		envMapIntensity: 0.25,
	} );

	for ( const name of [ 'mouth_tongue', 'mouth_teeth' ] ) {

		const part = byMat[ name ];
		if ( ! part ) continue;
		part.renderOrder = 12;
		Object.assign( part.material, {
			stencilWrite: true, stencilRef: 1, stencilFunc: THREE.EqualStencilFunc,
			stencilZPass: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, stencilFail: THREE.KeepStencilOp,
			envMapIntensity: 0.5,
		} );

	}

	for ( const m of Object.values( byMat ) ) m.material.needsUpdate = true;

}

function screenToWorld( clientX, clientY, out ) {

	const rect = renderer.domElement.getBoundingClientRect();
	pointerNDC.set(
		( ( clientX - rect.left ) / rect.width ) * 2 - 1,
		- ( ( clientY - rect.top ) / rect.height ) * 2 + 1
	);
	raycaster.setFromCamera( pointerNDC, camera );
	return raycaster.ray.intersectPlane( lookPlane, out ) ? out : null;

}

function onPointerMove( ev ) {

	const rect = renderer.domElement.getBoundingClientRect();
	const hz = HOTZONE.getBoundingClientRect();
	const inside = ( r ) => ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom;
	pointerInHotzone = inside( hz ) || inside( rect );
	lastPointerTime = performance.now();

	// Mid-presentation, a pointer coming close to the avatar takes its attention
	// for a few seconds. The cooldown is what makes it go back to the talk even
	// if the reader keeps the pointer there.
	if ( presenting() ) {

		const near = ev.clientX >= rect.left - PRESENT_NEAR && ev.clientX <= rect.right + PRESENT_NEAR
			&& ev.clientY >= rect.top - PRESENT_NEAR && ev.clientY <= rect.bottom + PRESENT_NEAR;
		if ( near && lastPointerTime >= present.attentionUntil + PRESENT_COOLDOWN_MS ) {

			present.attentionUntil = lastPointerTime + rand( PRESENT_ATTENTION_MS );

		}

	}

	screenToWorld( ev.clientX, ev.clientY, cursorPoint );

}

function onPointerOver( ev ) {

	const link = ev.target.closest ? ev.target.closest( LINK_SELECTOR ) : null;
	if ( link === hoverLink ) return;
	hoverLink = link;
	// Start on the cursor so the glance towards the camera reads as a second beat
	lookAtCamera = false;
	headSwitchAt = performance.now() + HEAD_SWITCH_MS;

}

// Aim at the start of the title text itself: the anchor's box can be far wider
// than its glyphs (centred headings), so measure the text range's first line.
const linkRange = document.createRange();
function updateLinkPoint() {

	if ( ! hoverLink || ! hoverLink.isConnected ) { hoverLink = null; return false; }
	linkRange.selectNodeContents( hoverLink );
	const rects = linkRange.getClientRects();
	const r = rects.length ? rects[ 0 ] : hoverLink.getBoundingClientRect();
	return screenToWorld( r.left + Math.min( 40, r.width / 2 ), r.top + r.height / 2, linkPoint ) !== null;

}

function updateLookTargets( now ) {

	if ( presenting() ) { presentLook( now ); return; }

	if ( hoverLink ) {

		if ( now >= headSwitchAt ) {

			lookAtCamera = ! lookAtCamera;
			headSwitchAt = now + HEAD_SWITCH_MS;

		}

		lookGoal.copy( lookAtCamera ? camera.position : cursorPoint );
		return;

	}

	// A pointer resting in the hotzone keeps the avatar's attention
	if ( pointerInHotzone || now - lastPointerTime < IDLE_AFTER_MS ) {

		lookGoal.copy( cursorPoint );
		return;

	}

	if ( now < idleNextChange ) return;
	idleNextChange = now + 2500 + Math.random() * 3500;
	// glance around, mostly ahead
	lookGoal.set( ( Math.random() - 0.5 ) * 2.4, - 0.3 + ( Math.random() - 0.3 ) * 1.4, LOOK_PLANE_Z );

}

function ease( current, target, rate, dt ) {

	return current + ( target - current ) * ( 1 - Math.exp( - rate * dt ) );

}

// Breathing: a slow torso rise/expand with the head bobbing in counter-phase.
// Returns the current breath phase in -1..1 so other parts can ride on it.
function updateBreath() {

	const phase = Math.sin( elapsed * 2 * Math.PI / BREATH_PERIOD );
	const inhale = ( phase + 1 ) / 2;   // 0..1
	torso.position.copy( torsoRestPos );
	torso.position.y += 0.012 * inhale;
	torso.scale.set( 1 + 0.012 * inhale, 1 + 0.008 * inhale, 1 + 0.015 * inhale );
	// tiny forward/back lean so the head gets a visible cadence
	tmpE.set( 0.018 * phase, 0, 0.004 * Math.sin( elapsed * 2 * Math.PI / ( BREATH_PERIOD * 1.9 ) ) );
	torso.quaternion.copy( torsoRestQuat ).multiply( tmpQ3.setFromEuler( tmpE ) );
	return phase;

}

function scheduleBlink() {

	nextBlinkAt = elapsed + 2.2 + Math.random() * 4.5;

}

function updateBlink( dt ) {

	if ( elapsed >= nextBlinkAt ) {

		scheduleBlink();
		const wink = Math.random() < 0.12;
		const side = Math.random() < 0.5 ? 'L' : 'R';
		for ( const s of [ 'L', 'R' ] ) if ( ! wink || s === side ) blinkPhase[ s ] = 1e-6;
		// occasional double blink
		if ( ! wink && Math.random() < 0.25 ) nextBlinkAt = elapsed + 0.35;

	}

	for ( const s of [ 'L', 'R' ] ) {

		let target = expr.blink[ s ];
		if ( blinkPhase[ s ] > 0 ) {

			blinkPhase[ s ] += dt;
			const dur = 0.24;
			const t = blinkPhase[ s ] / dur;
			if ( t >= 1 ) blinkPhase[ s ] = 0;
			else target = Math.max( target, Math.sin( Math.PI * Math.min( 1, t ) ) );

		}

		// closing is fast, opening a touch slower
		const rate = target > expr.blinkNow[ s ] ? 40 : 18;
		expr.blinkNow[ s ] = ease( expr.blinkNow[ s ], target, rate, dt );

	}

}

function scheduleEarEvent() {

	nextEarEventAt = elapsed + 3 + Math.random() * 7;

}

function updateEars( dt ) {

	// spontaneous flicks / droops while resting
	if ( ! earEvent && elapsed >= nextEarEventAt ) {

		scheduleEarEvent();
		const side = Math.random() < 0.5 ? 'L' : 'R';
		const kind = Math.random() < 0.65 ? 'flick' : 'droop';
		earEvent = { side, kind, t0: elapsed, dur: kind === 'flick' ? 0.42 : 2.4 };

	}

	for ( const s of [ 'L', 'R' ] ) {

		let flick = expr.ear[ s ].flick;
		let tilt = expr.ear[ s ].tilt;

		if ( earEvent && earEvent.side === s ) {

			const t = ( elapsed - earEvent.t0 ) / earEvent.dur;
			if ( t >= 1 ) earEvent = null;
			else if ( earEvent.kind === 'flick' ) flick += ( s === 'L' ? - 0.7 : 0.45 ) * Math.sin( Math.PI * t );
			else tilt += ( s === 'L' ? - 0.25 : 0.4 ) * Math.sin( Math.PI * t );   // droop / sag outwards

		}

		const now = expr.earNow[ s ];
		const rate = earEvent && earEvent.side === s && earEvent.kind === 'flick' ? 60 : 8;
		now.flick = ease( now.flick, flick, rate, dt );
		now.tilt = ease( now.tilt, tilt, rate, dt );

		// bone-local flick/tilt on top of the rest pose (as in the Blender pose tests)
		const f = face[ s ];
		tmpE.set( now.flick, 0, now.tilt );
		f.ear.quaternion.copy( f.earRestQuat ).multiply( tmpQ.setFromEuler( tmpE ) );

	}

}

function updateFace( dt, breath ) {

	updateBlink( dt );
	updateEars( dt );

	expr.narrowNow = ease( expr.narrowNow, expr.narrow, 6, dt );
	expr.browRaiseNow = ease( expr.browRaiseNow, expr.browRaise, 6, dt );

	for ( const s of [ 'L', 'R' ] ) {

		const f = face[ s ];
		// lid: open value + narrow squint + blink (blink wins)
		const closed = Math.max( expr.blinkNow[ s ], 0.45 * expr.narrowNow );
		f.lid.scale.y = THREE.MathUtils.lerp( LID_OPEN, 1.0, closed );
		// brow: follows the lid a little on blinks, drops when narrowing, raises on demand
		let drop = 0.35 * expr.blinkNow[ s ] * 0.04 + 0.05 * expr.narrowNow - 0.045 * expr.browRaiseNow;
		drop += 0.0025 * breath;   // breathing carries the brows very slightly
		f.brow.position.copy( f.browRestPos );
		f.brow.position.y += drop;

	}

	// mouth: explicit expression or speech amplitude
	const open = Math.max( expr.mouthOpen, speechAmp );
	const wide = Math.max( expr.mouthWide, speechAmp * 0.5 );
	expr.mouthOpenNow = ease( expr.mouthOpenNow, open, 22, dt );
	expr.mouthWideNow = ease( expr.mouthWideNow, wide, 14, dt );
	face.mouth.scale.set(
		THREE.MathUtils.lerp( 0.4, 1.3, expr.mouthWideNow ),
		THREE.MathUtils.lerp( 0.05, 1.0, expr.mouthOpenNow ),
		1
	);

}

function updateHead( dt, breath ) {

	lookPoint.lerp( lookGoal, 1 - Math.exp( - HEAD_SMOOTH * dt ) );

	head.getWorldPosition( tmpV );
	const dir = tmpV2.subVectors( lookPoint, tmpV ).normalize();
	const fwd = tmpV.set( 0, 0, 1 );   // rest forward in world space
	const angle = fwd.angleTo( dir );
	tmpQ.setFromUnitVectors( fwd, dir );
	if ( angle > HEAD_MAX_ANGLE ) tmpQ.slerp( tmpQ2.identity(), 1 - HEAD_MAX_ANGLE / angle );
	// breathing: a slow nod in counter-phase to the torso plus a faint roll
	tmpE.set( - 0.012 * breath, 0, 0.006 * Math.sin( elapsed * 2 * Math.PI / ( BREATH_PERIOD * 1.6 ) ) );
	tmpQ.multiply( tmpQ3.setFromEuler( tmpE ) );

	// local = parentInv * delta * parent * rest
	head.parent.getWorldQuaternion( parentQ );
	parentQInv.copy( parentQ ).invert();
	head.quaternion.copy( parentQInv ).multiply( tmpQ ).multiply( parentQ ).multiply( headRestQuat );

}

function updateArms( dt, now, linkVisible ) {

	// Presenting owns the arms while it runs. Otherwise: hovering a post title
	// puts the right paw on the title and the left paw towards the viewer, and
	// failing that the arm on the cursor's side points; the other rests.
	const pointAt = { L: null, R: null };
	if ( presenting() ) {

		presentArms( now, pointAt );

	} else if ( linkVisible ) {

		pointAt.R = linkPoint;
		pointAt.L = camera.position;

	} else if ( pointerInHotzone ) {

		pointAt[ lookPoint.x >= 0 ? 'L' : 'R' ] = lookPoint;

	}

	const k = 1 - Math.exp( - ARM_SMOOTH * dt );
	let moved = false;
	for ( const side of [ 'L', 'R' ] ) {

		const arm = arms[ side ];
		arm.pointing = pointAt[ side ] !== null;
		if ( arm.pointing ) {

			arm.upper.getWorldPosition( tmpV );
			tmpV2.subVectors( pointAt[ side ], tmpV ).normalize();
			arm.goal.copy( tmpV ).addScaledVector( tmpV2, ARM_REACH );

		} else {
			// Ease back to the authored rest pose rather than an arbitrary IK solution
			arm.goal.copy( arm.restTarget );
			for ( let i = 0; i < 2; i ++ ) {

				if ( arm.links[ i ].quaternion.angleTo( arm.restQuats[ i ] ) > 1e-4 ) {

					arm.links[ i ].quaternion.slerp( arm.restQuats[ i ], k );
					moved = true;

				}

			}

		}

		if ( arm.target.distanceToSquared( arm.goal ) > 1e-8 ) {

			arm.target.lerp( arm.goal, k );
			if ( arm.pointing ) moved = true;

		} else if ( arm.pointing ) {

			arm.pointing = false;   // settled: no need to re-solve

		}

		arm.ik.position.copy( arm.ik.parent.worldToLocal( tmpV.copy( arm.target ) ) );

	}

	return moved;

}

function solveArms() {

	scene.updateMatrixWorld( true );
	for ( const side of [ 'L', 'R' ] ) {

		const arm = arms[ side ];
		if ( ! arm.pointing ) continue;
		// Solving from rest every frame keeps the elbow bend deterministic
		for ( let i = 0; i < 2; i ++ ) arm.links[ i ].quaternion.copy( arm.restQuats[ i ] );
		arm.upper.updateMatrixWorld( true );
		ikSolver.updateOne( arm.chain );

	}

}

function animate() {

	timer.update();
	const dt = Math.min( timer.getDelta(), 0.1 );
	placePin( dt );
	if ( ! skinned ) {

		if ( needsRender ) { renderer.render( scene, camera ); needsRender = false; }
		return;

	}

	const now = performance.now();
	elapsed += dt;
	const linkVisible = updateLinkPoint();
	updateLookTargets( now );

	// Interaction-driven expression: brows up for a hovered title, squint a little
	// at the cursor when it is being followed, otherwise relax. Presenting keeps
	// a lighter brow raise on the beats where it addresses the room.
	if ( presenting() ) {

		expr.narrow = 0;
		expr.browRaise = present.gazeCamera ? 0.35 : 0.15;

	} else {

		expr.narrow = ( ! linkVisible && pointerInHotzone ) ? 0.35 : 0;
		expr.browRaise = linkVisible ? 0.6 : 0;

	}

	const breath = updateBreath();
	updateHead( dt, breath );
	updateFace( dt, breath );
	const armsMoved = updateArms( dt, now, linkVisible );
	if ( armsMoved ) solveArms();

	// Breathing never settles, so render every frame while the tab is visible.
	if ( ! document.hidden || needsRender ) {

		renderer.render( scene, camera );
		needsRender = false;

	}

}
