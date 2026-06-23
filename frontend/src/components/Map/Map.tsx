import { useEffect, useState } from "react";
import {
  GeoJSON,
  MapContainer,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";

import "leaflet/dist/leaflet.css";
import "./Map.css";

import MapSidebar from "../MapSidebar/MapSidebar";
import SwotCogLayer from "../SwotCogLayer";

const SWOT_TRACK_CATALOG_URL = "/data/swot_full_tracks.geojson";

const DISPLAY_MIN = -0.2;
const DISPLAY_MAX = 0.2;

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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Draw the lightweight full-pass SWOT track catalog.
 *
 * This uses plain Leaflet instead of React-Leaflet's GeoJSON component
 * because it was more reliable for your current setup.
 */
function SwotTrackLayer({
  data,
  selectedPassId,
  onSelect,
}: {
  data: any;
  selectedPassId?: string;
  onSelect: (pass: SwotPassProperties) => void;
}) {
  const map = useMap();

  useEffect(() => {
    if (!data) return;

    console.log("ACTIVE manual SWOT track layer");
    console.log("Track feature count:", data?.features?.length);

    const trackLayer = L.geoJSON(data, {
      style: (feature) => {
        const props =
          feature?.properties as SwotPassProperties | undefined;

        const isSelected = props?.id === selectedPassId;

        return {
          color: isSelected ? "#f97316" : "#38bdf8",
          weight: isSelected ? 4 : 3,
          opacity: 1,
        };
      },

      onEachFeature: (feature, layer) => {
        const props = feature.properties as SwotPassProperties;

        layer.bindPopup(`
          <div class="swot-popup">
            <strong>
              ${props.name || `SWOT Cycle ${props.cycle} · Pass ${props.pass}`}
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
            <em>Click this path to load its SSHA swath and nadir track.</em>
          </div>
        `);

        layer.on("click", () => {
          console.log("Clicked SWOT pass:", props);
          onSelect(props);
        });

        layer.on("mouseover", () => {
          if ("setStyle" in layer) {
            (layer as L.Path).setStyle({
              weight: 5,
              opacity: 1,
            });
          }
        });

        layer.on("mouseout", () => {
          const isSelected = props.id === selectedPassId;

          if ("setStyle" in layer) {
            (layer as L.Path).setStyle({
              color: isSelected ? "#f97316" : "#38bdf8",
              weight: isSelected ? 4 : 3,
              opacity: 1,
            });
          }
        });
      },
    });

    trackLayer.addTo(map);
    trackLayer.bringToFront();

    const bounds = trackLayer.getBounds();

    console.log("Track layer bounds:", bounds);

    if (bounds.isValid()) {
      map.fitBounds(bounds, {
        padding: [50, 50],
        maxZoom: 3,
      });
    }

    return () => {
      map.removeLayer(trackLayer);
    };
  }, [data, map, selectedPassId, onSelect]);

  return null;
}

export default function Map() {
  const [trackCatalog, setTrackCatalog] = useState<any>(null);

  const [selectedPass, setSelectedPass] =
    useState<SwotPassProperties | null>(null);

  const [selectedNadir, setSelectedNadir] = useState<any>(null);

  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  /**
   * Load the lightweight full-pass track catalog.
   */
  useEffect(() => {
    const controller = new AbortController();

    async function loadTrackCatalog() {
      try {
        setCatalogLoading(true);
        setCatalogError(null);

        console.log("Fetching catalog:", SWOT_TRACK_CATALOG_URL);

        const catalog = await loadGeoJson(
          SWOT_TRACK_CATALOG_URL,
          controller.signal
        );

        console.log("Loaded SWOT full-track catalog:", catalog);
        console.log("Number of catalog features:", catalog?.features?.length);

        setTrackCatalog(catalog);
      } catch (error) {
        if (isAbortError(error)) return;

        const message =
          error instanceof Error ? error.message : "Unknown catalog error";

        console.error("Could not load SWOT track catalog:", error);
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
   * When the user clicks a pass, load that pass's nadir GeoJSON.
   * The COG is loaded separately by SwotCogLayer.
   */
  useEffect(() => {
    if (!selectedPass) {
      setSelectedNadir(null);
      setDetailError(null);
      setDetailsLoading(false);
      return;
    }

    const pass = selectedPass;
    const controller = new AbortController();

    async function loadSelectedNadir() {
      try {
        setSelectedNadir(null);
        setDetailError(null);
        setDetailsLoading(true);

        console.log("Loading selected nadir:", pass.nadir_url);

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
        if (isAbortError(error)) return;

        const message =
          error instanceof Error ? error.message : "Unknown nadir error";

        console.error("Could not load selected nadir:", error);
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

  const selectedLabel = selectedPass
    ? `SWOT Cycle ${selectedPass.cycle} · Pass ${selectedPass.pass}`
    : "SWOT Pass Explorer";

  let toolbarMessage =
    "Click any SWOT path to load its SSHA swath and nadir track.";

  if (catalogLoading) {
    toolbarMessage = "Loading SWOT pass tracks…";
  } else if (catalogError) {
    toolbarMessage = catalogError;
  } else if (selectedPass && detailsLoading) {
    toolbarMessage = "Loading selected pass details…";
  } else if (selectedPass && detailError) {
    toolbarMessage = detailError;
  } else if (selectedPass) {
    toolbarMessage = "Selected pass SSHA swath and nadir track displayed.";
  }

  return (
    <div className="map-object">
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

      <MapSidebar
        cycle={selectedPass?.cycle || "—"}
        pass={selectedPass?.pass || "—"}
        product={selectedPass?.product || "L3 Expert"}
        variable={selectedPass?.variable || "ssha_unfiltered"}
        sourceResolution="2 km posting"
        outputGrid="0.025° full-pass display grid"
        resamplingMethod="Nearest neighbour"
        displayMin={DISPLAY_MIN}
        displayMax={DISPLAY_MAX}
        passSelected={Boolean(selectedPass)}
        initialExpanded={true}
      />

      <MapContainer
        className="leaflet-map"
        center={[20, -30]}
        zoom={3}
        minZoom={2}
        maxZoom={12}
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {trackCatalog && (
          <SwotTrackLayer
            data={trackCatalog}
            selectedPassId={selectedPass?.id}
            onSelect={setSelectedPass}
          />
        )}

        {selectedPass && (
          <SwotCogLayer
            url={selectedPass.cog_url}
            pane="overlayPane"
            displayMin={DISPLAY_MIN}
            displayMax={DISPLAY_MAX}
            renderResolution={128}
            opacity={0.75}
            fitBounds={true}
          />
        )}

        {selectedNadir && (
          <GeoJSON
            key={`${selectedPass?.id || "selected"}-nadir-casing`}
            data={selectedNadir}
            interactive={false}
            style={{
              color: "#ffffff",
              weight: 5,
              opacity: 0.95,
              lineCap: "round",
              lineJoin: "round",
            }}
          />
        )}

        {selectedNadir && (
          <GeoJSON
            key={`${selectedPass?.id || "selected"}-nadir-line`}
            data={selectedNadir}
            interactive={false}
            style={{
              color: "#ef6f61",
              weight: 2,
              opacity: 1,
              dashArray: "5 5",
              lineCap: "round",
              lineJoin: "round",
            }}
          />
        )}
      </MapContainer>
    </div>
  );
}