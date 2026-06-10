import { useEffect, useState } from "react";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./Map.css";
import SwotCogLayer from "../SwotCogLayer";

type SwotFeatureProperties = {
  name?: string;
  pass?: number | string;
  cycle?: number | string;
  time_start?: string;
  time_end?: string;
  cog_url?: string;
};

export default function Map() {
  const [swotPassData, setSwotPassData] = useState<any>(null);

  // This stores the COG currently selected by the user.
  // null means no COG layer is displayed.
  const [selectedCogUrl, setSelectedCogUrl] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/swot_pass_147_full_track.geojson")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load SWOT GeoJSON");
        }
        return response.json();
      })
      .then((data) => {
        setSwotPassData(data);
      })
      .catch((error) => {
        console.error("Error loading SWOT GeoJSON:", error);
      });
  }, []);

  const swotPassStyle = {
    color: "#00d4ff",
    weight: 4,
    opacity: 0.95,
  };

  const onEachSwotFeature = (feature: any, layer: any) => {
    const props: SwotFeatureProperties = feature.properties || {};

    // For now, hard-code the COG URL if it is not already in the GeoJSON.
    // Later, each GeoJSON feature should have its own cog_url property.
    const cogUrl =
      props.cog_url || "/data/swot_pass_147_ssha_unfiltered_cog.tif";

    layer.bindPopup(`
      <div class="swot-popup">
        <strong>${props.name || "SWOT Pass"}</strong><br/>
        Pass: ${props.pass || "147"}<br/>
        Cycle: ${props.cycle || "014"}<br/>
        Start: ${props.time_start || "N/A"}<br/>
        End: ${props.time_end || "N/A"}<br/>
        <em>Click the pass line to load the SSHA swath.</em>
      </div>
    `);

    // This is the important part:
    // clicking the line sets the selected COG URL.
    layer.on("click", () => {
      setSelectedCogUrl(cogUrl);
    });
  };

  return (
    <div className="map-object">
      <div className="map-toolbar">
        <div>
          <strong>SWOT Visualization</strong>
          <span className="map-toolbar-subtitle">
            {selectedCogUrl
              ? "SSHA swath loaded"
              : "Click a SWOT pass line to load SSHA"}
          </span>
        </div>

        {selectedCogUrl && (
          <button
            className="map-toolbar-button"
            onClick={() => setSelectedCogUrl(null)}
          >
            Remove SSHA Layer
          </button>
        )}
      </div>

      <MapContainer
        center={[20, -30]}
        zoom={3}
        minZoom={2}
        maxZoom={10}
        scrollWheelZoom={true}
        className="leaflet-map"
      >
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {selectedCogUrl && <SwotCogLayer url={selectedCogUrl} />}

        {swotPassData && (
          <GeoJSON
            data={swotPassData}
            style={swotPassStyle}
            onEachFeature={onEachSwotFeature}
          />
        )}
      </MapContainer>
    </div>
  );
}