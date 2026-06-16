import { useEffect, useState } from "react";
import {
  GeoJSON,
  MapContainer,
  Pane,
  TileLayer,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "./Map.css";
import MapSidebar from "../MapSidebar/MapSidebar";
import SwotCogLayer from "../SwotCogLayer";

/**
 * Files created from SWOT cycle 014, pass 091.
 *
 * Anything inside frontend/public/data is available in the browser under
 * /data/<filename>.
 */
const PASS_91_FULL_TRACK_URL =
  "/data/swot_cycle_014_pass_091_full_track.geojson";

const PASS_91_NADIR_URL =
  "/data/swot_cycle_014_pass_091_nadir.geojson";

const PASS_91_COG_URL =
  "/data/swot_cycle_014_pass_091_ssha_unfiltered_cog.tif";

const DISPLAY_MIN = -0.2;
const DISPLAY_MAX = 0.2;

type SwotFeatureProperties = {
  name?: string;
  pass?: number | string;
  cycle?: number | string;
  time_start?: string;
  time_end?: string;
};

/** Load one GeoJSON file and provide a useful error if it fails. */
async function loadGeoJson(url: string, signal: AbortSignal) {
  const response = await fetch(url, { signal });

  if (!response.ok) {
    throw new Error(
      `Failed to load ${url}: ${response.status} ${response.statusText}`
    );
  }

  return response.json();
}

export default function Map() {
  /** Thin full-pass line displayed before the pass is selected. */
  const [passTrackData, setPassTrackData] = useState<any>(null);

  /** Actual nadir line displayed above the COG after selection. */
  const [nadirData, setNadirData] = useState<any>(null);

  /** Controls whether the COG and nadir layers are visible. */
  const [passSelected, setPassSelected] = useState(false);

  /** Load the full-track and nadir GeoJSON files when the map starts. */
  useEffect(() => {
    const controller = new AbortController();

    async function loadFullTrack() {
      try {
        const fullTrack = await loadGeoJson(
          PASS_91_FULL_TRACK_URL,
          controller.signal
        );

        console.log("Loaded full SWOT track:", fullTrack);
        setPassTrackData(fullTrack);
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        console.error("Could not load full SWOT track:", error);
      }
    }

    async function loadNadirTrack() {
      try {
        const nadirTrack = await loadGeoJson(
          PASS_91_NADIR_URL,
          controller.signal
        );

        console.log("Loaded SWOT nadir track:", nadirTrack);
        setNadirData(nadirTrack);
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        console.error("Could not load SWOT nadir track:", error);
      }
    }

    loadFullTrack();
    loadNadirTrack();

    return () => {
      controller.abort();
    };
  }, []);

  /** Add popup information and click behavior to the full-track line. */
  function onEachPassFeature(feature: any, layer: any) {
    const props: SwotFeatureProperties = feature.properties || {};

    layer.bindPopup(`
      <div class="swot-popup">
        <strong>${props.name || "SWOT Pass Line"}</strong><br/>
        Pass: ${props.pass || "091"}<br/>
        Cycle: ${props.cycle || "014"}<br/>
        Start: ${props.time_start || "N/A"}<br/>
        End: ${props.time_end || "N/A"}<br/>
        <em>Click the line to display SSHA and the nadir track.</em>
      </div>
    `);

    layer.on("click", () => {
      setPassSelected(true);
    });
  }

  return (
    <div className="map-object">
      <div className="map-toolbar">
        <div>
          <strong>SWOT Cycle 014 · Pass 091</strong>

          <span className="map-toolbar-subtitle">
            {passSelected
              ? "SSHA swath and nadir track displayed"
              : "Click the thin SWOT pass line to load SSHA"}
          </span>
        </div>

        {passSelected && (
          <button
            type="button"
            className="map-toolbar-button"
            onClick={() => setPassSelected(false)}
          >
            Remove SSHA Layer
          </button>
        )}
      </div>

      <MapSidebar
        cycle="014"
        pass="091"
        product="L3 Expert"
        variable="ssha_unfiltered"
        sourceResolution="2 km posting"
        outputGrid="0.0025° (~250 m display grid)"
        resamplingMethod="Nearest neighbour"
        displayMin={DISPLAY_MIN}
        displayMax={DISPLAY_MAX}
        passSelected={passSelected}
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
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Keep the COG below all vector layers. */}
        <Pane name="swot-raster-pane" style={{ zIndex: 350 }} />

        {/* Load the SSHA COG only after the pass line is selected. */}
        {passSelected && (
          <SwotCogLayer
            url={PASS_91_COG_URL}
            pane="swot-raster-pane"
            displayMin={DISPLAY_MIN}
            displayMax={DISPLAY_MAX}
            renderResolution={128}
          />
        )}

        {/* Before selection, show the thin clickable full-pass track. */}
        <Pane name="swot-pass-pane" style={{ zIndex: 650 }}>
          {!passSelected && passTrackData && (
            <GeoJSON
              key="pass-91-full-track"
              data={passTrackData}
              style={{
                color: "#38bdf8",
                weight: 2,
                opacity: 0.9,
                lineCap: "round",
                lineJoin: "round",
              }}
              onEachFeature={onEachPassFeature}
            />
          )}
        </Pane>

        {/* After selection, show the nadir vector above the COG. */}
        <Pane name="swot-nadir-pane" style={{ zIndex: 700 }}>
          {passSelected && nadirData && (
            <GeoJSON
              key="pass-91-nadir-casing"
              data={nadirData}
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

          {passSelected && nadirData && (
            <GeoJSON
              key="pass-91-nadir-line"
              data={nadirData}
              interactive={false}
              style={{
                color: "#ef6f61",
                weight: 2,
                opacity: 1,
                dashArray: "4 5",
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
