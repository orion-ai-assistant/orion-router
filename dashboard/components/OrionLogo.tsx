'use client';

import React, { useEffect, useState } from 'react';

const SRC_SET = [
  '/dashboard/logo-72.png 2x',
  '/dashboard/logo-108.png 3x',
  '/dashboard/logo-144.png 4x',
  '/dashboard/logo-216.png 6x',
  '/dashboard/logo-288.png 8x',
].join(', ');

/**
 * The Orion logo, drawn at every size by scripts/make_icons.py (36..288 px).
 *
 * A browser picks a srcSet file once, for the scale of that moment. Zooming in later (Ctrl + wheel) or moving
 * the window to a sharper screen does not make it ask for a larger one: the small file was stretched and the
 * logo turned blurry. A new <img> for each scale (devicePixelRatio, which includes the zoom) picks again.
 */
export default function OrionLogo({ className }: { className?: string }) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    let query: MediaQueryList | null = null;
    const watch = () => {
      const ratio = window.devicePixelRatio || 1;
      setScale(ratio);
      query?.removeEventListener('change', watch);
      // Fires once the scale moves away from the current one, whichever way.
      query = window.matchMedia(`(resolution: ${ratio}dppx)`);
      query.addEventListener('change', watch);
    };
    watch();
    return () => query?.removeEventListener('change', watch);
  }, []);

  return <img key={scale} src="/dashboard/logo-36.png" srcSet={SRC_SET} alt="Orion Logo" className={className} />;
}
