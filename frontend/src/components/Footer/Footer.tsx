// src/components/Footer/Footer.tsx
import React from 'react';
import './Footer.css';

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner container">
        <p className="footer-text"> {new Date().getFullYear()} CSUN Mosaics </p>
      </div>
    </footer>
  );
}