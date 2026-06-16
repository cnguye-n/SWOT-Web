import { useEffect, useState } from "react";
import {
  GeoJSON,
  MapContainer,
  Pane,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";

import "leaflet/dist/leaflet.css";
import "./Map.css";

import MapSidebar from "../MapSidebar/MapSidebar";
import SwotCogLayer from "../SwotCogLayer";

/**
 * The catalog contains the lightweight full-track LineString for every pass.
 *
 * Because the file is inside:
 * frontend/public/data/
 *
 * Vite serves it at:
 * /data/swot_full_tracks.geojson
 */
const SWOT_TRACK_CATALOG_URL = "/data/swot_full_tracks.geojson";

const DISPLAY_MIN = -0.2;
const DISPLAY_MAX = 0.2;

/**
 * Metadata stored in each feature inside swot_full_tracks.geojson.
 */
type SwotPassProperties = {
  id: string;
  name?: string;
  source_file?: string;

  cycle: string;
  pass: string;

  time_start?: string;
  time_end?: string;

  product?: string;
  variable?: string;

  nadir_url: string;
  cog_url: string;
};

/**
 * Fetch a GeoJSON file and throw a useful error when the file cannot load.
 */
async function loadGeoJson(
  url: string,
  signal: AbortSignal
): Promise<any> {
  const response = await fetch(url, { signal });

  if (!response.ok) {
    throw new Error(
      `Failed to load ${url}: ${response.status} ${response.statusText}`
    );
  }

  return response.json();
}

/**
 * Check whether an error happened because the fetch request was cancelled.
 */
function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    error.name === "AbortError"
  );
}

/**
 * Move the Leaflet map so the complete track catalog is visible.
 *
 * This runs after the catalog finishes loading.
 */
function FitCatalogBounds({ data }: { data: any }) {
  const map = useMap();

  useEffect(() => {
    if (!data) {
      return;
    }

    const temporaryLayer = L.geoJSON(data);
    const bounds = temporaryLayer.getBounds();

    console.log("SWOT catalog bounds:", bounds);

    if (bounds.isValid()) {
      map.fitBounds(bounds, {
        padding: [30, 30],
        maxZoom: 4,
      });
    }
  }, [data, map]);

  return null;
}

export default function Map() {
  /**
   * The full lightweight catalog containing every pass track.
   */
  const [trackCatalog, setTrackCatalog] =
    useState<any>(null);

  /**
   * The metadata for the pass that the user clicked.
   */
  const [selectedPass, setSelectedPass] =
    useState<SwotPassProperties | null>(null);

  /**
   * The nadir GeoJSON for only the selected pass.
   */
  const [selectedNadir, setSelectedNadir] =
    useState<any>(null);

  /**
   * Loading and error states.
   */
  const [catalogLoading, setCatalogLoading] =
    useState(true);

  const [catalogError, setCatalogError] =
    useState<string | null>(null);

  const [detailsLoading, setDetailsLoading] =
    useState(false);

  const [detailError, setDetailError] =
    useState<string | null>(null);

  /**
   * Load the full-track catalog once when the map component starts.
   *
   * This does not load any COGs.
   */
  useEffect(() => {
    const controller = new AbortController();

    async function loadTrackCatalog() {
      try {
        setCatalogLoading(true);
        setCatalogError(null);

        const catalog = await loadGeoJson(
          SWOT_TRACK_CATALOG_URL,
          controller.signal
        );

        console.log(
          "Loaded SWOT full-track catalog:",
          catalog
        );

        console.log(
          "Number of catalog features:",
          catalog?.features?.length
        );

        setTrackCatalog(catalog);
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }

        const message =
          error instanceof Error
            ? error.message
            : "Unknown catalog error";

        console.error(
          "Could not load SWOT track catalog:",
          error
        );

        setCatalogError(message);
      } finally {
        if (!controller.signal.aborted) {
          setCatalogLoading(false);
        }
      }
    }

    loadTrackCatalog();

    return () => {
      controller.abort();
    };
  }, []);

  /**
   * Load only the nadir GeoJSON belonging to the selected pass.
   *
   * The COG is loaded separately by SwotCogLayer.
   */
  useEffect(() => {
    if (!selectedPass) {
      setSelectedNadir(null);
      setDetailError(null);
      setDetailsLoading(false);
      return;
    }

    /**
     * Save selectedPass in a local constant.
     *
     * This tells TypeScript that it cannot become null during
     * this asynchronous operation.
     */
    const pass = selectedPass;

    const controller = new AbortController();

    async function loadSelectedNadir() {
      try {
        setSelectedNadir(null);
        setDetailError(null);
        setDetailsLoading(true);

        console.log(
          "Loading selected nadir:",
          pass.nadir_url
        );

        const nadir = await loadGeoJson(
          pass.nadir_url,
          controller.signal
        );

        console.log(
          `Loaded nadir for cycle ${pass.cycle}, pass ${pass.pass}:`,
          nadir
        );

        setSelectedNadir(nadir);
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }

        const message =
          error instanceof Error
            ? error.message
            : "Unknown nadir error";

        console.error(
          "Could not load selected nadir:",
          error
        );

        setDetailError(message);
      } finally {
        if (!controller.signal.aborted) {
          setDetailsLoading(false);
        }
      }
    }

    loadSelectedNadir();

    return () => {
      controller.abort();
    };
  }, [selectedPass]);

  /**
   * Add popup, hover, and click behavior to every full-track feature.
   */
  function onEachPassFeature(
    feature: any,
    layer: any
  ) {
    const props =
      feature.properties as SwotPassProperties;

    layer.bindPopup(`
      <div class="swot-popup">
        <strong>
          ${
            props.name ||
            `SWOT Cycle ${props.cycle} · Pass ${props.pass}`
          }
        </strong>
        <br/>

        Cycle: ${props.cycle}
        <br/>

        Pass: ${props.pass}
        <br/>

        Start: ${props.time_start || "N/A"}
        <br/>

        End: ${props.time_end || "N/A"}
        <br/>

        <em>
          Click this path to load its nadir track and SSHA COG.
        </em>
      </div>
    `);

    layer.on({
      /**
       * Make the path easier to see when the cursor is over it.
       */
      mouseover: () => {
        layer.setStyle({
          weight: 7,
          opacity: 1,
        });

        layer.bringToFront();
      },

      /**
       * Restore the normal or selected style.
       */
      mouseout: () => {
        const isSelected =
          props.id === selectedPass?.id;

        layer.setStyle({
          color: isSelected
            ? "#f97316"
            : "#ff00ff",
          weight: isSelected ? 6 : 4,
          opacity: isSelected ? 1 : 0.9,
        });
      },

      /**
       * Save the clicked pass.
       *
       * This causes that pass's COG and nadir file to load.
       */
      click: () => {
        console.log("Selected SWOT pass:", props);
        setSelectedPass(props);
      },
    });
  }

  /**
   * Text displayed in the toolbar.
   */
  const selectedLabel = selectedPass
    ? `SWOT Cycle ${selectedPass.cycle} · Pass ${selectedPass.pass}`
    : "SWOT Pass Explorer";

  let toolbarMessage =
    "Click any SWOT path to load its SSHA and nadir track.";

  if (catalogLoading) {
    toolbarMessage = "Loading SWOT pass tracks…";
  } else if (catalogError) {
    toolbarMessage = catalogError;
  } else if (selectedPass && detailsLoading) {
    toolbarMessage =
      "Loading selected pass details…";
  } else if (selectedPass && detailError) {
    toolbarMessage = detailError;
  } else if (selectedPass) {
    toolbarMessage =
      "Selected pass SSHA and nadir track displayed.";
  }

  return (
    <div className="map-object">
      {/* Map toolbar */}
      <div className="map-toolbar">
        <div>
          <strong>{selectedLabel}</strong>

          <span className="map-toolbar-subtitle">
            {toolbarMessage}
          </span>
        </div>

        {selectedPass && (
          <button
            type="button"
            className="map-toolbar-button"
            onClick={() => {
              setSelectedPass(null);
              setSelectedNadir(null);
              setDetailError(null);
            }}
          >
            Close Selected Pass
          </button>
        )}
      </div>

      {/* Collapsible information sidebar */}
      <MapSidebar
        cycle={selectedPass?.cycle || "—"}
        pass={selectedPass?.pass || "—"}
        product={
          selectedPass?.product || "L3 Expert"
        }
        variable={
          selectedPass?.variable ||
          "ssha_unfiltered"
        }
        sourceResolution="2 km posting"
        outputGrid="0.0025° (~250 m display grid)"
        resamplingMethod="Nearest neighbour"
        displayMin={DISPLAY_MIN}
        displayMax={DISPLAY_MAX}
        passSelected={Boolean(selectedPass)}
        initialExpanded={true}
      />

      <MapContainer
        center={[20, -30]}
        zoom={3}
        minZoom={2}
        maxZoom={12}
        scrollWheelZoom={true}
        className="leaflet-map"
      >
        {/* Base map */}
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/*
          Automatically move the map so the complete track
          catalog is visible after it loads.
        */}
        {trackCatalog && (
          <FitCatalogBounds data={trackCatalog} />
        )}

        {/*
          Raster pane.

          The COG is drawn below all vector lines.
        */}
        <Pane
          name="swot-raster-pane"
          style={{ zIndex: 350 }}
        />

        {/*
          Load only the selected pass's COG.

          No COG is loaded when selectedPass is null.
        */}
        {selectedPass && (
          <SwotCogLayer
            key={selectedPass.id}
            url={selectedPass.cog_url}
            pane="swot-raster-pane"
            displayMin={DISPLAY_MIN}
            displayMax={DISPLAY_MAX}
            renderResolution={128}
            fitBounds={true}
          />
        )}

        {/*
          Full pass tracks.

          Every pass remains visible, even after one is selected.
        */}
        <Pane
          name="swot-pass-pane"
          style={{ zIndex: 650 }}
        >
          {trackCatalog && (
            <GeoJSON
              key={`swot-track-catalog-${
                selectedPass?.id || "none"
              }`}
              data={trackCatalog}
              style={(feature) => {
                const props =
                  feature?.properties as
                    | SwotPassProperties
                    | undefined;

                const isSelected =
                  props?.id === selectedPass?.id;

                return {
                  /**
                   * Bright magenta makes unselected paths
                   * very easy to see during testing.
                   */
                  color: isSelected
                    ? "#f97316"
                    : "#ff00ff",

                  weight: isSelected ? 6 : 4,
                  opacity: isSelected ? 1 : 0.9,
                  lineCap: "round",
                  lineJoin: "round",
                };
              }}
              onEachFeature={onEachPassFeature}
            />
          )}
        </Pane>

        {/*
          Selected pass's nadir line.

          It is rendered twice:
          1. Thick white casing
          2. Thin dashed coral line
        */}
        <Pane
          name="swot-nadir-pane"
          style={{ zIndex: 700 }}
        >
          {selectedNadir && (
            <GeoJSON
              key={`${
                selectedPass?.id || "selected"
              }-nadir-casing`}
              data={selectedNadir}
              interactive={false}
              style={{
                color: "#ffffff",
                weight: 6,
                opacity: 0.95,
                lineCap: "round",
                lineJoin: "round",
              }}
            />
          )}

          {selectedNadir && (
            <GeoJSON
              key={`${
                selectedPass?.id || "selected"
              }-nadir-line`}
              data={selectedNadir}
              interactive={false}
              style={{
                color: "#ef6f61",
                weight: 3,
                opacity: 1,
                dashArray: "5 5",
                lineCap: "round",
                lineJoin: "round",
              }}
            />
          )}
        </Pane>
      </MapContainer>
    </div>
  );
}