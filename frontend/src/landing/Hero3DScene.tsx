import React, { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float, Line, MeshWobbleMaterial, Sparkles } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import * as THREE from 'three';

// 1. Glassy Quality Score Panel
function QualityScoreCard({ position }: { position: [number, number, number] }) {
  const ringRef = useRef<THREE.Mesh>(null!);

  useFrame((_, delta) => {
    if (ringRef.current) {
      ringRef.current.rotation.z += delta * 0.8;
      ringRef.current.rotation.x += delta * 0.4;
    }
  });

  return (
    <Float speed={2} rotationIntensity={0.3} floatIntensity={0.8} position={position}>
      <group>
        {/* Main Physical Glass Slab */}
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[2.8, 1.8, 0.15]} />
          <meshPhysicalMaterial
            color="#ffffff"
            transmission={0.88}
            opacity={1}
            transparent
            roughness={0.1}
            ior={1.45}
            thickness={0.5}
            reflectivity={0.9}
            clearcoat={1}
            emissive="#8B5CF6"
            emissiveIntensity={0.15}
          />
        </mesh>

        {/* Outer Accent Wireframe */}
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[2.84, 1.84, 0.12]} />
          <meshBasicMaterial color="#A855F7" wireframe transparent opacity={0.4} />
        </mesh>

        {/* Spinning Score Torus */}
        <mesh ref={ringRef} position={[-0.8, 0.2, 0.15]}>
          <torusGeometry args={[0.35, 0.08, 16, 32]} />
          <meshStandardMaterial color="#06B6D4" emissive="#06B6D4" emissiveIntensity={0.8} roughness={0.2} />
        </mesh>

        {/* Indicator Spheres (Pass signals) */}
        <mesh position={[0.4, 0.4, 0.15]}>
          <sphereGeometry args={[0.1, 16, 16]} />
          <meshStandardMaterial color="#10B981" emissive="#10B981" emissiveIntensity={1} />
        </mesh>
        <mesh position={[0.8, 0.4, 0.15]}>
          <sphereGeometry args={[0.1, 16, 16]} />
          <meshStandardMaterial color="#10B981" emissive="#10B981" emissiveIntensity={1} />
        </mesh>
        <mesh position={[1.2, 0.4, 0.15]}>
          <sphereGeometry args={[0.1, 16, 16]} />
          <meshStandardMaterial color="#3B82F6" emissive="#3B82F6" emissiveIntensity={1} />
        </mesh>

        <mesh position={[0.5, -0.4, 0.15]}>
          <boxGeometry args={[1.4, 0.12, 0.05]} />
          <meshStandardMaterial color="#7C3AED" emissive="#7C3AED" emissiveIntensity={0.6} />
        </mesh>
      </group>
    </Float>
  );
}

// 2. Glassy Playwright Execution Panel
function PlaywrightExecCard({ position }: { position: [number, number, number] }) {
  const sphereRef = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (sphereRef.current) {
      sphereRef.current.position.y = Math.sin(state.clock.elapsedTime * 2) * 0.15;
    }
  });

  return (
    <Float speed={2.4} rotationIntensity={0.4} floatIntensity={1.2} position={position}>
      <group>
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[2.5, 1.6, 0.15]} />
          <meshPhysicalMaterial
            color="#ffffff"
            transmission={0.85}
            transparent
            roughness={0.15}
            ior={1.5}
            thickness={0.4}
            clearcoat={0.9}
            emissive="#3B82F6"
            emissiveIntensity={0.15}
          />
        </mesh>

        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[2.54, 1.64, 0.12]} />
          <meshBasicMaterial color="#3B82F6" wireframe transparent opacity={0.4} />
        </mesh>

        <mesh ref={sphereRef} position={[-0.7, 0, 0.2]}>
          <sphereGeometry args={[0.3, 32, 32]} />
          <MeshWobbleMaterial color="#2563EB" factor={0.4} speed={2} roughness={0.1} emissive="#2563EB" emissiveIntensity={0.8} />
        </mesh>

        <mesh position={[0.5, 0.3, 0.15]}>
          <boxGeometry args={[1.1, 0.08, 0.02]} />
          <meshBasicMaterial color="#94A3B8" />
        </mesh>
        <mesh position={[0.4, 0.0, 0.15]}>
          <boxGeometry args={[0.9, 0.08, 0.02]} />
          <meshStandardMaterial color="#7C3AED" emissive="#7C3AED" emissiveIntensity={0.6} />
        </mesh>
        <mesh position={[0.6, -0.3, 0.15]}>
          <boxGeometry args={[1.3, 0.08, 0.02]} />
          <meshStandardMaterial color="#10B981" emissive="#10B981" emissiveIntensity={0.6} />
        </mesh>
      </group>
    </Float>
  );
}

// 3. Glassy Security & Bug Panel
function SecurityShieldCard({ position }: { position: [number, number, number] }) {
  const shieldRef = useRef<THREE.Mesh>(null!);

  useFrame((_, delta) => {
    if (shieldRef.current) {
      shieldRef.current.rotation.y += delta * 0.9;
      shieldRef.current.rotation.x += delta * 0.3;
    }
  });

  return (
    <Float speed={1.8} rotationIntensity={0.5} floatIntensity={1} position={position}>
      <group>
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[2.2, 1.5, 0.15]} />
          <meshPhysicalMaterial
            color="#ffffff"
            transmission={0.88}
            transparent
            roughness={0.1}
            ior={1.45}
            thickness={0.4}
            clearcoat={1}
            emissive="#06B6D4"
            emissiveIntensity={0.15}
          />
        </mesh>

        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[2.24, 1.54, 0.12]} />
          <meshBasicMaterial color="#06B6D4" wireframe transparent opacity={0.4} />
        </mesh>

        <mesh ref={shieldRef} position={[-0.5, 0, 0.25]}>
          <octahedronGeometry args={[0.4, 0]} />
          <meshStandardMaterial color="#8B5CF6" emissive="#8B5CF6" emissiveIntensity={0.9} metalness={0.8} roughness={0.2} />
        </mesh>

        <mesh position={[0.4, 0.2, 0.15]}>
          <boxGeometry args={[0.8, 0.18, 0.05]} />
          <meshStandardMaterial color="#EF4444" emissive="#EF4444" emissiveIntensity={0.8} />
        </mesh>
        <mesh position={[0.4, -0.2, 0.15]}>
          <boxGeometry args={[0.8, 0.18, 0.05]} />
          <meshStandardMaterial color="#10B981" emissive="#10B981" emissiveIntensity={0.8} />
        </mesh>
      </group>
    </Float>
  );
}

// Connector Lines with Scan Pulse Effect
function ConnectingLines() {
  const lineRef1 = useRef<any>(null!);
  const lineRef2 = useRef<any>(null!);

  const p1: [number, number, number] = [-1.8, 1.2, 0];
  const p2: [number, number, number] = [1.8, -0.2, 0.5];
  const p3: [number, number, number] = [-0.4, -1.4, -0.2];

  useFrame((state) => {
    if (lineRef1.current) lineRef1.current.material.dashOffset = -state.clock.elapsedTime * 2;
    if (lineRef2.current) lineRef2.current.material.dashOffset = -state.clock.elapsedTime * 2.5;
  });

  return (
    <>
      <Line
        ref={lineRef1}
        points={[p1, p2]}
        color="#8B5CF6"
        lineWidth={2.5}
        dashed
        dashScale={8}
        dashSize={0.5}
      />
      <Line
        ref={lineRef2}
        points={[p2, p3]}
        color="#06B6D4"
        lineWidth={2.5}
        dashed
        dashScale={8}
        dashSize={0.5}
      />
    </>
  );
}

// Lerped Mouse Parallax & Continuous Gentle Auto-Rotation
function SceneParallaxGroup({ children }: { children: React.ReactNode }) {
  const groupRef = useRef<THREE.Group>(null!);

  useFrame((state, delta) => {
    // Gentle continuous rotation
    groupRef.current.rotation.y += delta * 0.15;

    // Damped lerping toward pointer position
    const targetX = (state.pointer.x * Math.PI) / 10;
    const targetY = (state.pointer.y * Math.PI) / 10;

    groupRef.current.rotation.y = THREE.MathUtils.lerp(groupRef.current.rotation.y, targetX, 0.04);
    groupRef.current.rotation.x = THREE.MathUtils.lerp(groupRef.current.rotation.x, -targetY, 0.04);
  });

  return <group ref={groupRef}>{children}</group>;
}

export function Hero3DScene() {
  const [hasError, setHasError] = useState(false);

  return (
    <div className="w-full h-full min-h-[380px] relative pointer-events-auto flex items-center justify-center">
      {/* Background Ambient Glow Orbs */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[340px] h-[340px] bg-gradient-to-tr from-purple-600/30 via-cyan-500/20 to-blue-600/30 rounded-full blur-3xl pointer-events-none animate-pulse" />

      {/* Floating 3D AI Core Showcase Card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: [0, -10, 0] }}
        transition={{
          y: { duration: 6, repeat: Infinity, ease: 'easeInOut' },
          opacity: { duration: 0.8 },
          scale: { duration: 0.8 },
        }}
        className="relative z-10 w-full max-w-[390px] rounded-2xl border-2 border-purple-500/50 bg-slate-950/80 backdrop-blur-2xl shadow-2xl shadow-purple-500/40 p-3 overflow-hidden group hover:border-purple-400 transition-all"
      >
        {/* Top Header Bar */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-purple-500/20 mb-3 text-xs font-bold text-slate-300">
          <div className="flex items-center gap-2">

          </div>

        </div>

        {/* Generated 3D AI Core Image */}
        <div className="relative rounded-2xl overflow-hidden border border-purple-500/30 group-hover:scale-[1.02] transition-transform duration-500">
          <img
            src="/hero_3d_ai_core.png"
            alt="3D AI Quality Assurance Core"
            className="w-full h-auto object-cover rounded-2xl shadow-inner"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-transparent opacity-60" />
        </div>

        {/* Bottom Status Bar */}
        <div className="mt-3.5 px-3 py-2.5 rounded-xl bg-purple-950/60 border border-purple-500/30 flex items-center justify-between text-xs font-semibold text-slate-200">
          <div className="flex items-center gap-2">

          </div>

        </div>
      </motion.div>

      {/* Background Three.js Sparkles Layer */}
      {!hasError && (
        <div className="absolute inset-0 pointer-events-none z-0">
          <Canvas
            camera={{ position: [0, 0, 5], fov: 45 }}
            onCreated={({ gl }) => gl.setClearColor('#000000', 0)}
            onError={() => setHasError(true)}
          >
            <ambientLight intensity={1} />
            <Sparkles count={40} scale={6} size={3} speed={0.4} opacity={0.6} color="#8B5CF6" />
            <Sparkles count={30} scale={6} size={2.5} speed={0.3} opacity={0.5} color="#06B6D4" />
          </Canvas>
        </div>
      )}
    </div>
  );
}
