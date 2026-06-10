// @ts-ignore
import { useEffect } from "react";
import { useMap } from "react-leaflet";
import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import chroma from "chroma-js";

/**
 * Props for the SWOT COG layer.
 *
 * url is the path to the Cloud Optimized GeoTIFF file.
 * Example:
 * /data/swot_pass_91_gulf_stream_ssha_unfiltered_cog.tif
 */
type SwotCogLayerProps = {
  url: string;
};

export default function SwotCogLayer({ url }: SwotCogLayerProps) {
  /**
   * useMap() gives this component access to the Leaflet map object.
   * We need this so we can manually add and remove the raster layer.
   */
  const map = useMap();

  useEffect(() => {
    /**
     * layer stores the GeoRasterLayer after it is created.
     * We keep a reference so we can remove it when the component unmounts
     * or when the URL changes.
     */
    let layer: any;

    /**
     * cancelled prevents the code from adding a layer after the component
     * has already unmounted. This avoids weird bugs if the COG is still
     * loading while the user switches layers.
     */
    let cancelled = false;

    async function loadCog() {
      console.log("Loading SWOT COG:", url);

      /**
       * Fetch the COG from the public folder.
       *
       * In React/Vite, a file stored at:
       * frontend/public/data/example.tif
       *
       * is available in the browser as:
       * /data/example.tif
       */
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`Failed to load COG: ${url}`);
      }

      /**
       * Convert the downloaded file into an ArrayBuffer.
       * parseGeoraster needs the raw binary data from the GeoTIFF/COG.
       */
      const arrayBuffer = await response.arrayBuffer();

      /**
       * Parse the GeoTIFF/COG into a georaster object.
       * This object contains:
       * - raster values
       * - bounds
       * - projection/georeferencing info
       * - width/height
       */
      const georaster = await parseGeoraster(arrayBuffer);

      /**
       * If the component unmounted while the file was loading,
       * stop here and do not add anything to the map.
       */
      if (cancelled) return;

      /**
       * Matt Archer Figure 1 style uses caxis([-0.4, 0.4]).
       *
       * The SWOT SSHA values are in meters:
       * -0.4 m = -40 cm
       *  0.0 m = 0 cm
       * +0.4 m = +40 cm
       *
       * This range controls the DISPLAY colors only.
       * It does not change the actual SSHA data.
       */
      const COLOR_MIN = -0.4;
      const COLOR_MAX = 0.4;

      /**
       * Diverging SSHA color ramp:
       *
       * -40 cm   dark blue
       * -20 cm   light blue
       *   0 cm   white
       * +20 cm   orange
       * +40 cm   dark red
       *
       * This is good for SSHA because zero is meaningful:
       * negative anomaly = blue
       * positive anomaly = red
       */
      const colorScale = chroma
        .scale(["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"])
        .domain([COLOR_MIN, -0.2, 0, 0.2, COLOR_MAX]);

      /**
       * Create the Leaflet raster layer.
       *
       * GeoRasterLayer takes the numeric COG values and draws them on the map.
       * The pixelValuesToColorFn below tells it how to color each pixel.
       */
      layer = new GeoRasterLayer({
        georaster,

        /**
         * Opacity controls transparency.
         * 1.0 = fully opaque
         * 0.0 = fully transparent
         *
         * 0.85 keeps the SSHA strong while still letting some basemap show.
         */
        opacity: 0.85,

        /**
         * Rendering resolution for the browser display.
         *
         * Higher number = sharper but slower.
         * Lower number = faster but coarser.
         *
         * This does NOT create real scientific resolution.
         * The actual science resolution depends on the source SWOT product
         * and the Python rasterization step.
         */
        resolution: 256,

        /**
         * This function is called for each raster pixel.
         * It receives the raster value and returns a color.
         *
         * For a single-band SSHA COG, values[0] is the SSHA value in meters.
         */
        pixelValuesToColorFn: (values: number[]) => {
          const value = values[0];

          /**
           * Missing values should be transparent.
           * Returning null means "do not draw this pixel."
           */
          if (value === null || value === undefined || Number.isNaN(value)) {
            return null;
          }

          /**
           * Our COG uses -9999 as nodata.
           * Anything around that value should not be drawn.
           */
          if (value <= -9998) {
            return null;
          }

          /**
           * Clamp extreme values into the display range.
           *
           * Example:
           * If value = 0.7 m, we color it like 0.4 m.
           * If value = -0.9 m, we color it like -0.4 m.
           *
           * This prevents extreme outliers from breaking the color ramp.
           * It only affects color display, not the original data file.
           */
          const clampedValue = Math.max(
            COLOR_MIN,
            Math.min(COLOR_MAX, value)
          );

          /**
           * Convert the numeric SSHA value into a hex color.
           */
          return colorScale(clampedValue).hex();
        },
      });

      /**
       * Add the COG layer to the Leaflet map.
       */
      layer.addTo(map);

      /**
       * Zoom/pan the map to the bounds of the COG.
       * This is helpful while testing because it automatically jumps to the swath.
       */
      map.fitBounds(layer.getBounds());

      console.log("SWOT COG loaded.");
    }

    /**
     * Start loading the COG.
     * If something fails, print the error in the browser console.
     */
    loadCog().catch((error) => {
      console.error("Error loading SWOT COG:", error);
    });

    /**
     * Cleanup function.
     *
     * React calls this when:
     * - the component unmounts
     * - the url changes
     *
     * It prevents duplicate COG layers from stacking on the map.
     */
    return () => {
      cancelled = true;

      if (layer) {
        map.removeLayer(layer);
      }
    };
  }, [map, url]);

  /**
   * This component does not render normal HTML.
   * It only adds a Leaflet layer to the map.
   */
  return null;
}