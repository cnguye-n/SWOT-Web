import { useEffect } from "react";
import { useMap } from "react-leaflet";
import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import chroma from "chroma-js";

const georasterCache = new Map<string, Promise<any>>();

async function getGeoraster(url: string): Promise<any> {
  const cached = georasterCache.get(url);

  if (cached) {
    return cached;
  }

  const request = fetch(url)
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(
          `Failed to fetch COG ${url}: ${response.status} ${response.statusText}`
        );
      }

      const arrayBuffer = await response.arrayBuffer();

      console.log("Fetched COG bytes:", url, arrayBuffer.byteLength);

      return parseGeoraster(arrayBuffer);
    })
    .catch((error: unknown) => {
      georasterCache.delete(url);
      throw error;
    });

  georasterCache.set(url, request);

  return request;
}

type SwotCogLayerProps = {
  url: string;
  pane?: string;
  displayMin?: number;
  displayMax?: number;
  renderResolution?: number;
  opacity?: number;
  fitBounds?: boolean;
};

export default function SwotCogLayer({
  url,
  pane = "overlayPane",
  displayMin = -0.2,
  displayMax = 0.2,
  renderResolution = 128,
  opacity = 0.75,
  fitBounds = true,
}: SwotCogLayerProps) {
  const map = useMap();

  useEffect(() => {
    let layer: any = null;
    let cancelled = false;

    async function loadCog() {
      if (!(displayMin < 0 && displayMax > 0)) {
        throw new Error(
          "The SSHA display range must cross zero, such as -0.2 to 0.2."
        );
      }

      console.log("Loading SWOT COG:", url);

      const georaster = await getGeoraster(url);

      if (cancelled) {
        return;
      }

      const colorScale = chroma
        .scale([
          "#2166ac",
          "#67a9cf",
          "#f7f7f7",
          "#ef8a62",
          "#b2182b",
        ])
        .domain([
          displayMin,
          displayMin / 2,
          0,
          displayMax / 2,
          displayMax,
        ]);

      layer = new (GeoRasterLayer as any)({
        georaster,
        pane,
        opacity,
        resolution: renderResolution,
        resampleMethod: "nearest",
        updateWhenIdle: true,
        updateWhenZooming: false,
        keepBuffer: 2,
        debugLevel: 0,

        pixelValuesToColorFn: (values: number[]) => {
          const value = values[0];

          if (
            value === null ||
            value === undefined ||
            Number.isNaN(value) ||
            value <= -9998
          ) {
            return null;
          }

          const clampedValue = Math.max(
            displayMin,
            Math.min(displayMax, value)
          );

          return colorScale(clampedValue).hex();
        },
      });

      layer.addTo(map);

      if (fitBounds) {
        map.fitBounds(layer.getBounds(), {
          padding: [20, 20],
        });
      }

      console.log("SWOT COG loaded:", url);
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
  }, [
    map,
    url,
    pane,
    displayMin,
    displayMax,
    renderResolution,
    opacity,
    fitBounds,
  ]);

  return null;
}