declare module "georaster" {
  const parseGeoraster: (input: string | ArrayBuffer) => Promise<any>;
  export default parseGeoraster;
}

declare module "georaster-layer-for-leaflet" {
  const GeoRasterLayer: any;
  export default GeoRasterLayer;
}