import { useEffect } from "react";
import { useMap } from "react-leaflet";
import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import chroma from "chroma-js";

/**
 * Cache already-opened COGs.
 *
 * When the user hides and reopens the same pass,
 * the file metadata does not need to be parsed again.
 */
const georasterCache = new Map<string, Promise<any>>();

async function getGeoraster(url: string): Promise<any> {
  const cached = georasterCache.get(url);

  if (cached) {
    return cached;
  }

  /**
   * Passing the URL directly lets GeoRaster treat the file as a COG
   * and request raster sections as needed.
   *
   * The old code used:
   * fetch -> arrayBuffer -> parseGeoraster
   *
   * That required downloading the complete TIFF before displaying it.
   */
  const request = parseGeoraster(url).catch((error: unknown) => {
    georasterCache.delete(url);
    throw error;
  });

  georasterCache.set(url, request);
  return request;
}

type SwotCogLayerProps = {
  /** Browser path such as /data/pass_091.tif */
  url: string;

  /** Leaflet pane where the raster should be drawn */
  pane?: string;

  /** SSHA display range in meters */
  displayMin?: number;
  displayMax?: number;

  /**
   * Number of raster samples rendered across and down
   * each Leaflet tile.
   */
  renderResolution?: number;

  opacity?: number;

  /** Move the map to the COG bounds when it opens */
  fitBounds?: boolean;
};

export default function SwotCogLayer({
  url,
  pane = "overlayPane",
  displayMin = -0.2,
  displayMax = 0.2,
  renderResolution = 128,
  opacity = 0.9,
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

      /**
       * Five-color diverging SSHA scale:
       *
       * -0.20 m = dark blue
       * -0.10 m = light blue
       *  0.00 m = white
       * +0.10 m = orange
       * +0.20 m = dark red
       */
      const negativeMidpoint = displayMin / 2;
      const positiveMidpoint = displayMax / 2;

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
          negativeMidpoint,
          0,
          positiveMidpoint,
          displayMax,
        ]);

      layer = new (GeoRasterLayer as any)({
        georaster,

        /**
         * Draw the raster below the pass and nadir vectors.
         */
        pane,

        opacity,

        /**
         * Browser rendering resolution only.
         * It does not change the scientific resolution of the COG.
         */
        resolution: renderResolution,

        /**
         * Do not blend neighboring values.
         */
        resampleMethod: "nearest",

        /**
         * Wait until map movement finishes before redrawing.
         */
        updateWhenIdle: true,
        updateWhenZooming: false,

        /**
         * Keep only a small number of off-screen tiles.
         */
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

          /**
           * Values beyond ±0.2 m receive the endpoint color.
           * This affects display only, not stored SSHA values.
           */
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