// src/components/Navbar/Navbar.tsx
import { Link, useLocation } from "react-router-dom";
import "./Navbar.css";

export default function Navbar() {
  const location = useLocation();

  function isActive(path: string) {
    if (path === "/map") {
      return location.pathname === "/" || location.pathname === "/map";
    }

    return location.pathname === path;
  }

  return (
    <nav className="navbar">
      <div className="nav-inner">
        <Link to="/" className="nav-logo">
          MOSAICS
        </Link>

        <ul className="nav-menu">
          <li>
            <Link
              to="/map"
              className={`nav-link${isActive("/map") ? " active" : ""}`}
            >
              Map
            </Link>
          </li>

          <li>
            <Link
              to="/about"
              className={`nav-link${isActive("/about") ? " active" : ""}`}
            >
              About
            </Link>
          </li>
        </ul>
      </div>
    </nav>
  );
}