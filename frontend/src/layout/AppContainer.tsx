// src/layout/AppContainer.tsx
import React from 'react';
import { useLocation } from "react-router-dom";
import Navbar from '../components/Navbar/Navbar';
import Footer from '../components/Footer/Footer';

interface AppContainerProps {
  children: React.ReactNode;
}

export default function AppContainer({ children }: AppContainerProps) {
  const location = useLocation();
  const hideFooter = location.pathname === "/" || location.pathname === "/map";
  return (
    <div className="app">
      <Navbar />
      <main>{children}</main>
      { !hideFooter && <Footer /> }
    </div>
  );
}