import { useState } from "react";
import "./MapSidebar.css";

type MapSidebarProps = {
  cycle: string;
  pass: string;
  product: string;
  variable: string;
  sourceResolution: string;
  outputGrid: string;
  resamplingMethod: string;
  displayMin: number;
  displayMax: number;
  passSelected: boolean;
  initialExpanded?: boolean;
};

function formatSigned(value: number): string {
  if (value > 0) {
    return `+${value.toFixed(2)}`;
  }

  return value.toFixed(2);
}

/**
 * Collapsible scientific guide for the SWOT map.
 *
 * The sidebar owns only its open/closed UI state. Map.tsx continues to own
 * all map-layer state, such as whether the pass has been selected.
 */
export default function MapSidebar({
  cycle,
  pass,
  product,
  variable,
  sourceResolution,
  outputGrid,
  resamplingMethod,
  displayMin,
  displayMax,
  passSelected,
  initialExpanded = true,
}: MapSidebarProps) {
  const [isExpanded, setIsExpanded] = useState(initialExpanded);

  const negativeMidpoint = displayMin / 2;
  const positiveMidpoint = displayMax / 2;

  return (
    <aside
      className={`map-sidebar ${
        isExpanded ? "map-sidebar--expanded" : "map-sidebar--collapsed"
      }`}
      aria-label="SWOT map data guide"
    >
      {!isExpanded ? (
        <button
          type="button"
          className="map-sidebar-collapsed-button"
          onClick={() => setIsExpanded(true)}
          aria-label="Expand SWOT data guide"
          title="Open SWOT data guide"
        >
          <span className="map-sidebar-info-icon" aria-hidden="true">
            i
          </span>
          <span className="map-sidebar-collapsed-label">Guide</span>
          <span className="map-sidebar-chevron" aria-hidden="true">
            ‹
          </span>
        </button>
      ) : (
        <>
          <header className="map-sidebar-header">
            <div>
              <strong>SWOT Data Guide</strong>
              <span>
                Cycle {cycle} · Pass {pass}
              </span>
            </div>

            <button
              type="button"
              className="map-sidebar-toggle"
              onClick={() => setIsExpanded(false)}
              aria-label="Collapse SWOT data guide"
              title="Collapse guide"
            >
              ›
            </button>
          </header>

          <div className="map-sidebar-content">
            <section className="map-sidebar-section">
              <h3>SSHA color scale</h3>

              <div
                className="map-sidebar-colorbar"
                role="img"
                aria-label={`Sea surface height anomaly color scale from ${displayMin} to ${displayMax} meters`}
              />

              <div className="map-sidebar-color-labels">
                <span>{formatSigned(displayMin)}</span>
                <span>{formatSigned(negativeMidpoint)}</span>
                <span>0.00</span>
                <span>{formatSigned(positiveMidpoint)}</span>
                <span>{formatSigned(displayMax)} m</span>
              </div>

              <div className="map-sidebar-color-description">
                <span>
                  <i className="map-sidebar-dot map-sidebar-dot--negative" />
                  Negative SSHA
                </span>

                <span>
                  <i className="map-sidebar-dot map-sidebar-dot--positive" />
                  Positive SSHA
                </span>
              </div>
            </section>

            <section className="map-sidebar-section">
              <h3>Resolution guide</h3>

              <table className="map-sidebar-table">
                <tbody>
                  <tr>
                    <th scope="row">Product</th>
                    <td>{product}</td>
                  </tr>
                  <tr>
                    <th scope="row">Variable</th>
                    <td>
                      <code>{variable}</code>
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Source grid</th>
                    <td>{sourceResolution}</td>
                  </tr>
                  <tr>
                    <th scope="row">Output grid</th>
                    <td>{outputGrid}</td>
                  </tr>
                  <tr>
                    <th scope="row">Resampling</th>
                    <td>{resamplingMethod}</td>
                  </tr>
                  <tr>
                    <th scope="row">Display range</th>
                    <td>
                      {formatSigned(displayMin)} to {formatSigned(displayMax)} m
                    </td>
                  </tr>
                </tbody>
              </table>

              <p className="map-sidebar-note">
                The output grid controls map display. It does not increase the
                scientific resolution of the source product.
              </p>
            </section>

            <section className="map-sidebar-section">
              <h3>Map layers</h3>

              <div className="map-sidebar-layer-key">
                <div className="map-sidebar-layer-row map-sidebar-layer-row--active">
                  <span className="map-layer-symbol map-layer-symbol--full-track" />
                  <span>Full pass track</span>
                </div>

                <div
                  className={`map-sidebar-layer-row ${
                    passSelected
                      ? "map-sidebar-layer-row--active"
                      : "map-sidebar-layer-row--inactive"
                  }`}
                >
                  <span className="map-layer-symbol map-layer-symbol--nadir" />
                  <span>Nadir track</span>
                </div>

                <div
                  className={`map-sidebar-layer-row ${
                    passSelected
                      ? "map-sidebar-layer-row--active"
                      : "map-sidebar-layer-row--inactive"
                  }`}
                >
                  <span className="map-layer-symbol map-layer-symbol--swath" />
                  <span>SSHA swath</span>
                </div>
              </div>
            </section>
          </div>

          <footer className="map-sidebar-status">
            <span
              className={`map-status-indicator ${
                passSelected ? "map-status-indicator--active" : ""
              }`}
              aria-hidden="true"
            />

            {passSelected
              ? "SSHA and nadir are displayed"
              : "Click the pass track to load data"}
          </footer>
        </>
      )}
    </aside>
  );
}
