// Semprini avatar: skinned GLB with pointer-driven head look-at and IK arm pointing.
// Coordinates (three.js, Y up): character faces +Z (towards the default camera).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { CCDIKSolver } from 'three/addons/animation/CCDIKSolver.js';

const container = document.querySelector( '.canvas-container' );
const MODEL_URL = container.dataset.model;
const HOTZONE = container.closest( '.about' ) || container;

const VIEW_WIDTH = 260;
const VIEW_HEIGHT = 260;
const HEAD_MAX_ANGLE = THREE.MathUtils.degToRad( 38 );
const HEAD_SMOOTH = 6;      // 1/s, larger = snappier
const ARM_SMOOTH = 4;
const ARM_REACH = 0.74;     // < upper arm + forearm so the elbow stays bent
const LOOK_PLANE_Z = 1.6;   // plane in front of the face that pointer rays hit
const IDLE_AFTER_MS = 4000;

let camera, scene, renderer, controls;
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
let pointerInHotzone = false;
let lastPointerTime = 0;
let idleNextChange = 0;
let needsRender = true;
const timer = new THREE.Timer();

init();

function init() {

	renderer = new THREE.WebGLRenderer( { antialias: true, alpha: true } );
	renderer.setPixelRatio( window.devicePixelRatio );
	renderer.setSize( VIEW_WIDTH, VIEW_HEIGHT );
	renderer.toneMapping = THREE.ACESFilmicToneMapping;
	container.appendChild( renderer.domElement );

	camera = new THREE.PerspectiveCamera( 45, VIEW_WIDTH / VIEW_HEIGHT, 0.25, 20 );
	camera.position.set( 0.3, -0.25, 3.6 );

	const pmremGenerator = new THREE.PMREMGenerator( renderer );
	scene = new THREE.Scene();
	scene.environment = pmremGenerator.fromScene( new RoomEnvironment(), 0.04 ).texture;

	new GLTFLoader().load( MODEL_URL, onModelLoaded );

	controls = new OrbitControls( camera, renderer.domElement );
	controls.addEventListener( 'change', () => { needsRender = true; } );
	controls.minDistance = 2;
	controls.maxDistance = 10;
	controls.target.set( 0, -0.25, 0 );
	controls.update();

	window.addEventListener( 'pointermove', onPointerMove, { passive: true } );
	window.addEventListener( 'blur', () => { pointerInHotzone = false; } );
	document.addEventListener( 'pointerleave', () => { pointerInHotzone = false; } );

	renderer.setAnimationLoop( animate );

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
	window.__avatarDebug = { arms, head, ikSolver, get inHot() { return pointerInHotzone; }, lookPoint };
	needsRender = true;

}

function onPointerMove( ev ) {

	const rect = renderer.domElement.getBoundingClientRect();
	pointerNDC.set(
		( ( ev.clientX - rect.left ) / rect.width ) * 2 - 1,
		- ( ( ev.clientY - rect.top ) / rect.height ) * 2 + 1
	);
	const hz = HOTZONE.getBoundingClientRect();
	const inside = ( r ) => ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom;
	pointerInHotzone = inside( hz ) || inside( rect );
	lastPointerTime = performance.now();

	raycaster.setFromCamera( pointerNDC, camera );
	if ( raycaster.ray.intersectPlane( lookPlane, tmpV ) ) lookGoal.copy( tmpV );

}

function updateIdle( now ) {

	// A pointer resting in the hotzone keeps the avatar's attention
	if ( pointerInHotzone || now - lastPointerTime < IDLE_AFTER_MS ) return;
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

function updateArms( dt ) {

	// Point with the arm on the same side as the cursor; the other rests.
	const pointingSide = pointerInHotzone ? ( lookPoint.x >= 0 ? 'L' : 'R' ) : null;
	const k = 1 - Math.exp( - ARM_SMOOTH * dt );
	let moved = false;
	for ( const side of [ 'L', 'R' ] ) {

		const arm = arms[ side ];
		arm.pointing = side === pointingSide;
		if ( arm.pointing ) {

			arm.upper.getWorldPosition( tmpV );
			tmpV2.subVectors( lookPoint, tmpV ).normalize();
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

	updateIdle( performance.now() );
	headPrevQ.copy( head.quaternion );
	updateHead( dt );
	const armsMoved = updateArms( dt );
	if ( armsMoved ) solveArms();

	if ( needsRender || armsMoved || headPrevQ.angleTo( head.quaternion ) > 1e-4 ) {

		renderer.render( scene, camera );
		needsRender = false;

	}

}
