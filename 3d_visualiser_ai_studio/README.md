# PalletVision: 3D Pallet Visualiser

A standalone React + Vite app, built in Google AI Studio, for inspecting a pallet plan in 3D. It loads a placement file exported by the engine (the **Placement CSV** download in the live app, or an `.xlsx` with a `Box_Coordinates` sheet) and lets you filter by pallet and layer, check heights and weights, and spot overhangs or failed placements.

The main [live app](https://palletization-capstone.streamlit.app) already includes a 3D view, so this is an extra tool for working with exported files.

## Run locally

Requires Node.js 18+.

```bash
cd 3d_visualiser_ai_studio
npm install
npm run dev
```

Then open http://localhost:3000. No API key is needed.

## Expected columns

One row per case: `Pallet_ID`, `Layer_ID`, `Box_ID`, `x_min`, `y_min`, `z_min`, `x_max`, `y_max`, `z_max`, `Número de material`, `Familia_detectada`, `Peso_bruto`, `Placement_Status`, `Placement_Warning`.

Created by Mohamad Bilal, Saif Rizvi and Alexandre Gallais as part of the UCD Smurfit capstone.
