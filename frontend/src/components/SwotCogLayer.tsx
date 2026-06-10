// @ts-ignore
import { useEffect } from "react";
import { useMap } from "react-leaflet";
import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import chroma from "chroma-js";

type SwotCogLayerProps = {
  url: string;
};

export default function SwotCogLayer({ url }: SwotCogLayerProps) {
  const map = useMap();

  useEffect(() => {
    let layer: any;
    let cancelled = false;

    async function loadCog() {
      console.log("Loading SWOT COG:", url);

      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`Failed to load COG: ${url}`);
      }

      const arrayBuffer = await response.arrayBuffer();
      const georaster = await parseGeoraster(arrayBuffer);

      if (cancelled) return;

      const colorScale = chroma
        .scale(["#2166ac", "#f7f7f7", "#b2182b"])
        .domain([-0.2, 0, 0.2]);

      layer = new GeoRasterLayer({
        georaster,

        // Slight transparency so the basemap can still be seen.
        opacity: 0.8,

        // Higher number = faster but coarser rendering.
        // Lower number = sharper but slower.
        resolution: 256,

        pixelValuesToColorFn: (values: number[]) => {
          const value = values[0];

          // No data / missing data should be transparent.
          if (value === null || value === undefined || Number.isNaN(value)) {
            return null;
          }

          // Your COG nodata value is -9999.
          if (value <= -9998) {
            return null;
          }

          // Clamp color range so extreme values do not break the color ramp.
          const clampedValue = Math.max(-0.2, Math.min(0.2, value));

          return colorScale(clampedValue).hex();
        },
      });

      layer.addTo(map);

      // Zoom to the COG bounds after loading.
      map.fitBounds(layer.getBounds());

      console.log("SWOT COG loaded.");
    }

    loadCog().catch((error) => {
      console.error("Error loading SWOT COG:", error);
    });

    return () => {
      cancelled = true;

      if (layer) {
        map.removeLayer(layer);
      }
    };
  }, [map, url]);

  return null;
}