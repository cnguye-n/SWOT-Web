import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppContainer from "./layout/AppContainer";

import MapPage from "./pages/MapPage/MapPage";
import AboutPage from "./pages/AboutPage/AboutPage";

export default function App() {
  return (
    <BrowserRouter>
      <AppContainer>
        <Routes>
          <Route path="/" element={<MapPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/about" element={<AboutPage />} />
        </Routes>
      </AppContainer>
    </BrowserRouter>
  );
}