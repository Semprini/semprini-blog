// Minimal GLB viewer for project heroes and 3D blocks.
//
// Deliberately not avatar.js: that module rigs one specific skeleton and grabs
// the first .canvas-container on the page. These viewports use their own class
// so the two never fight over an element.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function frameObject( object, camera ) {

	const box = new THREE.Box3().setFromObject( object );
	const size = box.getSize( new THREE.Vector3() );
	const center = box.getCenter( new THREE.Vector3() );

	object.position.sub( center );

	const extent = Math.max( size.x, size.y, size.z ) || 1;
	const distance = extent / ( 2 * Math.tan( ( camera.fov * Math.PI ) / 360 ) );
	camera.position.set( 0, extent * 0.15, distance * 1.6 );
	camera.near = distance / 100;
	camera.far = distance * 100;
	camera.updateProjectionMatrix();
	camera.lookAt( 0, 0, 0 );

}

function mount( container ) {

	const url = container.dataset.devcastModel;
	if ( ! url ) return;

	const renderer = new THREE.WebGLRenderer( { antialias: true, alpha: true } );
	renderer.setPixelRatio( Math.min( window.devicePixelRatio, 2 ) );
	renderer.setSize( container.clientWidth, container.clientHeight );

	const scene = new THREE.Scene();
	const camera = new THREE.PerspectiveCamera( 45, container.clientWidth / container.clientHeight, 0.1, 100 );
	scene.add( new THREE.HemisphereLight( 0xffffff, 0x333344, 2.2 ) );
	const key = new THREE.DirectionalLight( 0xffffff, 1.6 );
	key.position.set( 2, 4, 3 );
	scene.add( key );

	const pivot = new THREE.Group();
	scene.add( pivot );

	const spin = ! REDUCED_MOTION && container.dataset.autorotate !== 'false';
	let visible = true;

	new GLTFLoader().load(
		url,
		( gltf ) => {

			pivot.add( gltf.scene );
			frameObject( gltf.scene, camera );

			// Only replace the fallback link once there is something to show.
			container.textContent = '';
			container.appendChild( renderer.domElement );

			renderer.setAnimationLoop( () => {

				if ( ! visible ) return;
				if ( spin ) pivot.rotation.y += 0.004;
				renderer.render( scene, camera );

			} );

		},
		undefined,
		() => {
			// Loading failed - leave the download link in place.
			renderer.dispose();
		}
	);

	new ResizeObserver( () => {

		const { clientWidth: w, clientHeight: h } = container;
		if ( ! w || ! h ) return;
		renderer.setSize( w, h );
		camera.aspect = w / h;
		camera.updateProjectionMatrix();

	} ).observe( container );

	new IntersectionObserver( ( entries ) => {

		visible = entries[ 0 ].isIntersecting;

	} ).observe( container );

}

document.querySelectorAll( '.devcast-model-viewport' ).forEach( mount );
