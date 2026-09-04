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

const MAX_VIEW_WIDTH = 340;
const VIEW_ASPECT = 340 / 310;   // wide enough for a fully extended arm, tall enough for head to paw
const HEADER_RESERVE = 138;      // in-flow height the header keeps; the rest overhangs the page
const HEAD_MAX_ANGLE = THREE.MathUtils.degToRad( 38 );
const HEAD_SMOOTH = 6;      // 1/s, larger = snappier
const HEAD_SWITCH_MS = 1400;
const ARM_SMOOTH = 4;
const ARM_REACH = 0.74;     // < upper arm + forearm so the elbow stays bent
const LOOK_PLANE_Z = 1.6;   // plane in front of the face that pointer rays hit
const IDLE_AFTER_MS = 4000;
const CAM_TARGET = new THREE.Vector3( - 0.1, - 0.4, 0 );
const CAM_DIST = 3.8;

let camera, scene, renderer;
let skinned, ikSolver;
let head, headRestQuat;
const arms = {};            // side -> { ik, upper, hand, restTarget, target, active }
const tmpQ = new THREE.Quaternion();
const tmpQ2 = new THREE.Quaternion();
const parentQ = new THREE.Quaternion();
const parentQInv = new THREE.Quaternion();
const headPrevQ = new THREE.Quaternion();
const tmpV = new THREE.Vector3();
const tmpV2 = new THREE.Vector3();
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
const timer = new THREE.Timer();

init();

function init() {

	renderer = new THREE.WebGLRenderer( { antialias: true, alpha: true } );
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

// The canvas is fixed to the top of the viewport so the avatar stays put while the
// page scrolls; the container keeps its place in the header layout.
function layout() {

	const w = Math.round( Math.min( MAX_VIEW_WIDTH, Math.max( 180, window.innerWidth * 0.42 ) ) );
	const h = Math.round( w / VIEW_ASPECT );
	container.style.width = `${ w }px`;
	container.style.height = `${ h }px`;
	container.style.marginBottom = `${ Math.min( 0, HEADER_RESERVE - h ) }px`;
	renderer.setSize( w, h );
	camera.aspect = w / h;
	camera.updateProjectionMatrix();
	renderer.domElement.style.left = `${ Math.round( container.getBoundingClientRect().left ) }px`;
	needsRender = true;

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

	// GLTFLoader sanitises node names: Blender's "Hand.L" arrives as "HandL".
	const bones = skinned.skeleton.bones;
	const index = ( name ) => bones.findIndex( ( b ) => b.name === name );
	const bone = ( name ) => bones[ index( name ) ];

	head = bone( 'Head' );
	headRestQuat = head.quaternion.clone();

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
		arms, head, ikSolver, lookPoint, linkPoint, cursorPoint, camera, scene, renderer,
		get inHot() { return pointerInHotzone; },
		get link() { return hoverLink; },
		get lookAtCamera() { return lookAtCamera; },
	};
	needsRender = true;

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

// Aim at the start of the title text rather than the middle of a long line.
function updateLinkPoint() {

	if ( ! hoverLink || ! hoverLink.isConnected ) { hoverLink = null; return false; }
	const r = hoverLink.getBoundingClientRect();
	return screenToWorld( r.left + Math.min( 40, r.width / 2 ), r.top + r.height / 2, linkPoint ) !== null;

}

function updateLookTargets( now ) {

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

function updateHead( dt ) {

	lookPoint.lerp( lookGoal, 1 - Math.exp( - HEAD_SMOOTH * dt ) );

	head.getWorldPosition( tmpV );
	const dir = tmpV2.subVectors( lookPoint, tmpV ).normalize();
	const fwd = tmpV.set( 0, 0, 1 );   // rest forward in world space
	const angle = fwd.angleTo( dir );
	tmpQ.setFromUnitVectors( fwd, dir );
	if ( angle > HEAD_MAX_ANGLE ) tmpQ.slerp( tmpQ2.identity(), 1 - HEAD_MAX_ANGLE / angle );

	// local = parentInv * delta * parent * rest
	head.parent.getWorldQuaternion( parentQ );
	parentQInv.copy( parentQ ).invert();
	head.quaternion.copy( parentQInv ).multiply( tmpQ ).multiply( parentQ ).multiply( headRestQuat );

}

function updateArms( dt, linkVisible ) {

	// Hovering a post title: right paw at the title, left paw at the viewer.
	// Otherwise point with the arm on the same side as the cursor; the other rests.
	const pointAt = { L: null, R: null };
	if ( linkVisible ) {

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
	if ( ! skinned ) {

		if ( needsRender ) { renderer.render( scene, camera ); needsRender = false; }
		return;

	}

	const now = performance.now();
	const linkVisible = updateLinkPoint();
	updateLookTargets( now );
	headPrevQ.copy( head.quaternion );
	updateHead( dt );
	const armsMoved = updateArms( dt, linkVisible );
	if ( armsMoved ) solveArms();

	if ( needsRender || armsMoved || headPrevQ.angleTo( head.quaternion ) > 1e-4 ) {

		renderer.render( scene, camera );
		needsRender = false;

	}

}
