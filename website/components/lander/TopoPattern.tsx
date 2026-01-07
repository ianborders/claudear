'use client';

import { useMemo } from 'react';

interface TopoPatternProps {
  seed?: number;
  complexity?: 'simple' | 'medium' | 'complex';
  color?: string;
  opacity?: number;
  className?: string;
}

// Simple seeded random number generator
function seededRandom(seed: number) {
  let value = seed;
  return () => {
    value = (value * 9301 + 49297) % 233280;
    return value / 233280;
  };
}

// Generate smooth contour lines like a topographic map
function generateContourLines(
  width: number,
  height: number,
  seed: number,
  complexity: 'simple' | 'medium' | 'complex'
): string[] {
  const random = seededRandom(seed);
  const paths: string[] = [];

  // Number of contour rings
  const ringCount = {
    simple: 5,
    medium: 7,
    complex: 10,
  }[complexity];

  // Generate a center point (can be offset from actual center)
  const centerX = width * (0.3 + random() * 0.4);
  const centerY = height * (0.3 + random() * 0.4);

  // Generate control points for organic shape
  const numControlPoints = 8;
  const baseAngles: number[] = [];
  const baseRadii: number[] = [];

  for (let i = 0; i < numControlPoints; i++) {
    baseAngles.push((i / numControlPoints) * Math.PI * 2);
    // Vary the base radius to create organic shape
    baseRadii.push(0.8 + random() * 0.4);
  }

  // Generate concentric contour rings
  for (let ring = 0; ring < ringCount; ring++) {
    const ringProgress = (ring + 1) / (ringCount + 1);
    const baseRadius = Math.min(width, height) * 0.5 * ringProgress;

    // Build the contour path
    const points: { x: number; y: number }[] = [];
    const segments = 60; // Smooth curve

    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;

      // Interpolate radius from control points
      let radius = 0;
      for (let j = 0; j < numControlPoints; j++) {
        const angleDiff = Math.abs(angle - baseAngles[j]);
        const normalizedDiff = Math.min(angleDiff, Math.PI * 2 - angleDiff);
        const weight = Math.max(0, 1 - normalizedDiff / (Math.PI / 2));
        radius += baseRadii[j] * weight;
      }
      radius = radius / 2; // Normalize

      // Add some noise for natural variation
      const noise = 1 + Math.sin(angle * 3 + seed) * 0.1 + Math.sin(angle * 7 + seed * 2) * 0.05;

      const finalRadius = baseRadius * radius * noise;
      const x = centerX + Math.cos(angle) * finalRadius;
      const y = centerY + Math.sin(angle) * finalRadius;

      points.push({ x, y });
    }

    // Helper to round numbers for consistent server/client rendering
    const r = (n: number) => Math.round(n * 100) / 100;

    // Convert points to smooth bezier curve
    let path = `M ${r(points[0].x)} ${r(points[0].y)}`;

    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const curr = points[i];
      const next = points[(i + 1) % points.length];

      // Calculate control points for smooth curve
      const cp1x = prev.x + (curr.x - points[(i - 2 + points.length) % points.length].x) * 0.2;
      const cp1y = prev.y + (curr.y - points[(i - 2 + points.length) % points.length].y) * 0.2;
      const cp2x = curr.x - (next.x - prev.x) * 0.2;
      const cp2y = curr.y - (next.y - prev.y) * 0.2;

      path += ` C ${r(cp1x)} ${r(cp1y)}, ${r(cp2x)} ${r(cp2y)}, ${r(curr.x)} ${r(curr.y)}`;
    }

    path += ' Z'; // Close the path
    paths.push(path);
  }

  return paths;
}

export function TopoPattern({
  seed = 1,
  complexity = 'medium',
  color = '#9ca3af',
  opacity = 0.2,
  className = '',
}: TopoPatternProps) {
  const paths = useMemo(() => {
    return generateContourLines(400, 300, seed, complexity);
  }, [seed, complexity]);

  return (
    <svg
      className={`absolute inset-0 w-full h-full pointer-events-none ${className}`}
      viewBox="0 0 400 300"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
    >
      {paths.map((path, i) => (
        <path
          key={i}
          d={path}
          stroke={color}
          strokeWidth={1}
          strokeOpacity={opacity}
          fill="none"
        />
      ))}
    </svg>
  );
}
