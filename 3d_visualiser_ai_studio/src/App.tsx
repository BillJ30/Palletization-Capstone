import React, { useState, useMemo, useRef, useEffect } from 'react';
import * as XLSX from 'xlsx';
import { 
  Layers, 
  Upload, 
  AlertTriangle, 
  CheckCircle2, 
  Info, 
  RotateCw, 
  Maximize2, 
  Minimize2, 
  RotateCcw, 
  Search, 
  FileSpreadsheet, 
  Sliders, 
  Sparkles, 
  Compass, 
  Download,
  HelpCircle,
  TrendingUp,
  Scale
} from 'lucide-react';

// ============================================================================
// Types & Interfaces
// ============================================================================
interface Box {
  Box_ID: string;
  Pallet_ID: string;
  Layer_ID: number;
  x_min: number;
  y_min: number;
  z_min: number;
  x_max: number;
  y_max: number;
  z_max: number;
  material_number: string;
  family: string;
  weight: number;
  status: 'PLACED' | 'FAILED' | string;
  warning: string;
  // Computed properties
  volume: number;
  isFloating?: boolean;
  hasOverhang?: boolean;
  exceedsCeiling?: boolean;
  hasInvalidCoords?: boolean;
}

interface PalletSummary {
  palletId: string;
  totalBoxes: number;
  placedBoxes: number;
  failedBoxes: number;
  maxHeight: number;
  totalVolume: number; // cm³
  utilization: number; // %
  totalWeight: number; // kg
  overhangCount: number;
  ceilingCount: number;
  floatingCount: number;
}

// Color schemes matching "High Density" Slate/Red/Teal palette
const FAMILY_COLORS: { [key: string]: { fill: string; stroke: string; text: string; label?: string; rank?: number; desc?: string } } = {
  // LATAS (Cans) - Stable, bottom-to-middle ranks
  'LATAS_330': { fill: 'rgba(228, 30, 43, 0.7)', stroke: '#e41e2b', text: '#ef4444', label: 'Cans 330ml', rank: 3, desc: 'Standard 330ml Can Case' },
  'LATAS_500': { fill: 'rgba(16, 185, 129, 0.7)', stroke: '#10b981', text: '#10b981', label: 'Cans 500ml', rank: 2, desc: 'Tall 500ml Can Case (Energy)' },
  'LATAS_250': { fill: 'rgba(59, 130, 246, 0.7)', stroke: '#3b82f6', text: '#60a5fa', label: 'Cans 250ml', rank: 4, desc: 'Sleek 250ml Can Case' },
  'LATAS_200': { fill: 'rgba(236, 72, 153, 0.7)', stroke: '#ec4899', text: '#f472b6', label: 'Cans 200ml', rank: 5, desc: 'Mini 200ml Can Case' },
  'LATAS': { fill: 'rgba(168, 85, 247, 0.7)', stroke: '#a855f7', text: '#c084fc', label: 'Cans (Other)', rank: 3, desc: 'Standard Can Tray wrap' },

  // VR (Vidrio Retornable) - Heavy, bottom layers rank
  'VR_237': { fill: 'rgba(13, 148, 136, 0.75)', stroke: '#0d9488', text: '#2dd4bf', label: 'Returnable Glass 237ml', rank: 1, desc: 'Heavy returnable 237ml contour glass crate' },
  'VR_300': { fill: 'rgba(20, 184, 166, 0.75)', stroke: '#14b8a6', text: '#5eead4', label: 'Returnable Glass 300ml', rank: 1, desc: 'Heavy returnable 300ml glass crate' },
  'VR_350': { fill: 'rgba(15, 118, 110, 0.75)', stroke: '#0f7173', text: '#0f172a', label: 'Returnable Glass 350ml', rank: 1, desc: 'Heavy returnable 350ml glass crate' },
  'VR': { fill: 'rgba(4, 120, 87, 0.75)', stroke: '#047857', text: '#34d399', label: 'Returnable Glass', rank: 1, desc: 'Standard Returnable glass container' },

  // VNR (Vidrio No Retornable) - Moderate weight, middle layers rank
  'VNR_200': { fill: 'rgba(245, 158, 11, 0.7)', stroke: '#f59e0b', text: '#fbbf24', label: 'Glass 200ml', rank: 2, desc: 'Glass Non-Returnable 200ml Case' },
  'VNR_330': { fill: 'rgba(217, 119, 6, 0.7)', stroke: '#d97706', text: '#f59e0b', label: 'Glass 330ml', rank: 2, desc: 'Glass Non-Returnable 330ml Case' },
  'VNR': { fill: 'rgba(180, 83, 9, 0.7)', stroke: '#b45309', text: '#fb923c', label: 'Glass Bottle (Other)', rank: 2, desc: 'Glass Non-Returnable Bottle Case' },

  // PET (Plastic Bottles) - Light, top layers rank
  'PET_500': { fill: 'rgba(12, 74, 96, 0.65)', stroke: '#0e7490', text: '#cbd5e1', label: 'PET Bottles 500ml', rank: 6, desc: 'Plastic bottles 500ml tray wrap' },
  'PET_1000': { fill: 'rgba(14, 116, 144, 0.7)', stroke: '#0e7490', text: '#22d3ee', label: 'PET Bottles 1L', rank: 7, desc: 'Plastic bottles 1L tray wrap' },
  'PET_1250': { fill: 'rgba(6, 182, 212, 0.7)', stroke: '#06b6d4', text: '#67e8f9', label: 'PET Bottles 1.25L', rank: 8, desc: 'Plastic bottles 1.25L tray wrap' },
  'PET_1500': { fill: 'rgba(29, 78, 216, 0.7)', stroke: '#1d4ed8', text: '#60a5fa', label: 'PET Bottles 1.5L', rank: 9, desc: 'Plastic bottles 1.5L tray wrap' },
  'PET_1750': { fill: 'rgba(37, 99, 235, 0.7)', stroke: '#2563eb', text: '#93c5fd', label: 'PET Bottles 1.75L', rank: 10, desc: 'Plastic bottles 1.75L tray wrap' },
  'PET_2000': { fill: 'rgba(30, 58, 138, 0.7)', stroke: '#1e3a8a', text: '#3b82f6', label: 'PET Bottles 2L', rank: 11, desc: 'Plastic bottles 2L tray wrap' },
  'PET': { fill: 'rgba(71, 85, 105, 0.7)', stroke: '#64748b', text: '#94a3b8', label: 'PET Bottles (Other)', rank: 6, desc: 'Standard plastic bottles tray wrap' },

  'FAILED': { fill: 'rgba(239, 68, 68, 0.9)', stroke: '#f87171', text: '#f87171', label: 'Failed Placements', rank: 99, desc: 'Items that failed heuristic nesting rules' },
  'UNKNOWN': { fill: 'rgba(148, 163, 184, 0.75)', stroke: '#94a3b8', text: '#cbd5e1', label: 'Uncategorized', rank: 99, desc: 'Unidentified product packaging standard' },
};

// Standard pallet dims (cm)
const PALLET_WIDTH = 120;
const PALLET_DEPTH = 80;
const CEILING_LIMIT = 180.0; // 180cm height limit (pallet base included)

// ============================================================================
// Programmatic Sandbox/Mock Data Generators
// ============================================================================
const generateMockPallet1 = (): Box[] => {
  const boxes: Box[] = [];
  
  // Layer 1: LATAS_330 (40 x 30 x 15 cm, 12kg)
  const l1_boxes = [
    { x1: 0, y1: 0, x2: 40, y2: 30 },
    { x1: 40, y1: 0, x2: 80, y2: 30 },
    { x1: 80, y1: 0, x2: 120, y2: 30 },
    { x1: 0, y1: 30, x2: 40, y2: 60 },
    { x1: 40, y1: 30, x2: 80, y2: 60 },
    { x1: 80, y1: 30, x2: 120, y2: 60 },
    { x1: 0, y1: 60, x2: 40, y2: 80 },
    { x1: 40, y1: 60, x2: 80, y2: 80 },
    { x1: 80, y1: 60, x2: 120, y2: 80 }
  ];
  l1_boxes.forEach((b, idx) => {
    boxes.push({
      Box_ID: `BOX-L1-CAN-${100 + idx}`,
      Pallet_ID: 'PALLET_0824_01',
      Layer_ID: 1,
      x_min: b.x1, y_min: b.y1, z_min: 0,
      x_max: b.x2, y_max: b.y2, z_max: 15,
      material_number: '0010245 - Coca-Cola Classic 330ml Can Case',
      family: 'LATAS_330',
      weight: 12.0,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * 15
    });
  });

  // Layer 2: BOTELLAS_1500 (40 x 20 x 30 cm, 15.6kg)
  const l2_boxes = [
    { x1: 0, y1: 0, x2: 40, y2: 20 },
    { x1: 40, y1: 0, x2: 80, y2: 20 },
    { x1: 80, y1: 0, x2: 120, y2: 20 },
    { x1: 0, y1: 20, x2: 40, y2: 40 },
    { x1: 40, y1: 20, x2: 80, y2: 40 },
    { x1: 80, y1: 20, x2: 120, y2: 40 },
    { x1: 0, y1: 40, x2: 40, y2: 80 },
    { x1: 40, y1: 40, x2: 80, y2: 80 },
    { x1: 80, y1: 40, x2: 120, y2: 80 }
  ];
  l2_boxes.forEach((b, idx) => {
    boxes.push({
      Box_ID: `BOX-L2-BOT15-${200 + idx}`,
      Pallet_ID: 'PALLET_0824_01',
      Layer_ID: 2,
      x_min: b.x1, y_min: b.y1, z_min: 15,
      x_max: b.x2, y_max: b.y2, z_max: 45,
      material_number: '0010398 - Diet Coke 1.5L Pet 6-Pack',
      family: 'BOTELLAS_1500',
      weight: 15.6,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * 30
    });
  });

  // Layer 3: BOTELLAS_500 (30 x 20 x 24 cm, 10.5kg)
  const l3_boxes = [
    { x1: 0, y1: 0, x2: 30, y2: 20 },
    { x1: 30, y1: 0, x2: 60, y2: 20 },
    { x1: 60, y1: 0, x2: 90, y2: 20 },
    { x1: 90, y1: 0, x2: 120, y2: 20 },
    { x1: 0, y1: 20, x2: 30, y2: 40 },
    { x1: 30, y1: 20, x2: 60, y2: 40 },
    { x1: 60, y1: 20, x2: 90, y2: 40 },
    { x1: 90, y1: 20, x2: 120, y2: 40 },
    { x1: 0, y1: 40, x2: 30, y2: 60 },
    { x1: 30, y1: 40, x2: 60, y2: 60 },
    { x1: 60, y1: 40, x2: 90, y2: 60 },
    { x1: 90, y1: 40, x2: 120, y2: 60 },
    { x1: 0, y1: 60, x2: 30, y2: 80 },
    { x1: 30, y1: 60, x2: 60, y2: 80 },
    { x1: 60, y1: 60, x2: 90, y2: 80 },
    { x1: 90, y1: 60, x2: 120, y2: 80 }
  ];
  l3_boxes.forEach((b, idx) => {
    boxes.push({
      Box_ID: `BOX-L3-BOT50-${300 + idx}`,
      Pallet_ID: 'PALLET_0824_01',
      Layer_ID: 3,
      x_min: b.x1, y_min: b.y1, z_min: 45,
      x_max: b.x2, y_max: b.y2, z_max: 69,
      material_number: '0020412 - Sprite Zero 500ml Pack',
      family: 'BOTELLAS_500',
      weight: 10.5,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * 24
    });
  });

  // Layer 4: RETORNABLE (40 x 30 x 35 cm, 18.2kg)
  const l4_boxes = [
    { x1: 0, y1: 0, x2: 40, y2: 30 },
    { x1: 40, y1: 0, x2: 80, y2: 30 },
    { x1: 80, y1: 0, x2: 120, y2: 30 },
    { x1: 0, y1: 30, x2: 40, y2: 60 },
    { x1: 40, y1: 30, x2: 80, y2: 60 },
    { x1: 80, y1: 30, x2: 120, y2: 60 }
  ];
  l4_boxes.forEach((b, idx) => {
    boxes.push({
      Box_ID: `BOX-L4-RET-${400 + idx}`,
      Pallet_ID: 'PALLET_0824_01',
      Layer_ID: 4,
      x_min: b.x1, y_min: b.y1, z_min: 69,
      x_max: b.x2, y_max: b.y2, z_max: 104,
      material_number: '0010108 - Fanta Orange 1.25L Retornable Case',
      family: 'RETORNABLE',
      weight: 18.2,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * 35
    });
  });

  // Layer 5: VIDRIO (30 x 20 x 20 cm, 14.0kg)
  const l5_boxes = [
    { x1: 0, y1: 60, x2: 30, y2: 80 },
    { x1: 30, y1: 60, x2: 60, y2: 80 },
    { x1: 60, y1: 60, x2: 90, y2: 80 },
    { x1: 90, y1: 60, x2: 120, y2: 80 }
  ];
  l5_boxes.forEach((b, idx) => {
    boxes.push({
      Box_ID: `BOX-L4-GLS-${500 + idx}`,
      Pallet_ID: 'PALLET_0824_01',
      Layer_ID: 4, // grouped under same height plane
      x_min: b.x1, y_min: b.y1, z_min: 69,
      x_max: b.x2, y_max: b.y2, z_max: 89,
      material_number: '0032991 - Coca-Cola Glass Contour Bottle 24x355ml',
      family: 'VIDRIO',
      weight: 14.0,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * 20
    });
  });

  // Layer 6: AGUA (30 x 20 x 25 cm, 12.5kg)
  const l6_boxes = [
    { x1: 10, y1: 10, x2: 40, y2: 30 },
    { x1: 40, y1: 10, x2: 70, y2: 30 },
    { x1: 70, y1: 10, x2: 100, y2: 30 },
    { x1: 10, y1: 30, x2: 40, y2: 50 },
    { x1: 40, y1: 30, x2: 70, y2: 50 },
    { x1: 70, y1: 30, x2: 100, y2: 50 },
    { x1: 10, y1: 50, x2: 40, y2: 70 },
    { x1: 40, y1: 50, x2: 70, y2: 70 },
    { x1: 70, y1: 50, x2: 100, y2: 70 }
  ];
  l6_boxes.forEach((b, idx) => {
    boxes.push({
      Box_ID: `BOX-L5-H2O-${600 + idx}`,
      Pallet_ID: 'PALLET_0824_01',
      Layer_ID: 5,
      x_min: b.x1, y_min: b.y1, z_min: 104,
      x_max: b.x2, y_max: b.y2, z_max: 129,
      material_number: '0055110 - Ciel Purified Still Water 1L 12-Pack',
      family: 'AGUA',
      weight: 12.5,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * 25
    });
  });

  return boxes;
};

const generateMockPallet2 = (): Box[] => {
  const boxes: Box[] = [];
  
  // Layer 1: Normal boxes
  const normal_boxes = [
    { x1: 0, y1: 0, x2: 40, y2: 40, z1: 0, z2: 25, fam: 'BOTELLAS_500', m: '0020412 - Sprite Pack' },
    { x1: 40, y1: 0, x2: 80, y2: 40, z1: 0, z2: 25, fam: 'BOTELLAS_500', m: '0020412 - Sprite Pack' },
    { x1: 0, y1: 40, x2: 40, y2: 80, z1: 0, z2: 25, fam: 'BOTELLAS_500', m: '0020412 - Sprite Pack' },
    { x1: 40, y1: 40, x2: 80, y2: 80, z1: 0, z2: 25, fam: 'BOTELLAS_500', m: '0020412 - Sprite Pack' },
  ];
  normal_boxes.forEach((b, idx) => {
    boxes.push({
      Box_ID: `DEMO-OK-${100 + idx}`,
      Pallet_ID: 'PALLET_0824_02',
      Layer_ID: 1,
      x_min: b.x1, y_min: b.y1, z_min: b.z1,
      x_max: b.x2, y_max: b.y2, z_max: b.z2,
      material_number: b.m,
      family: b.fam,
      weight: 10.5,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * (b.z2 - b.z1)
    });
  });

  // Deliberate Overhangs
  boxes.push({
    Box_ID: `WARN-OVERHANG-X`,
    Pallet_ID: 'PALLET_0824_02',
    Layer_ID: 1,
    x_min: 80, y_min: 0, z_min: 0,
    x_max: 126, y_max: 40, z_max: 25, // Overhangs X-axis by 6cm
    material_number: '0010398 - Diet Coke 1.5L Pet (Overhang Case)',
    family: 'BOTELLAS_1500',
    weight: 15.6,
    status: 'PLACED',
    warning: 'Width overhang exceeds limits (>120cm base)',
    volume: 46 * 40 * 25
  });

  boxes.push({
    Box_ID: `WARN-OVERHANG-Y`,
    Pallet_ID: 'PALLET_0824_02',
    Layer_ID: 1,
    x_min: 80, y_min: 40, z_min: 0,
    x_max: 120, y_max: 86, z_max: 25, // Overhangs Y-axis by 6cm
    material_number: '0010398 - Diet Coke 1.5L Pet (Overhang Case)',
    family: 'BOTELLAS_1500',
    weight: 15.6,
    status: 'PLACED',
    warning: 'Depth overhang exceeds limits (>80cm base)',
    volume: 40 * 46 * 25
  });

  // Layer 2: Normal layer
  const l2 = [
    { x1: 0, y1: 0, x2: 40, y2: 40, z1: 25, z2: 60, fam: 'LATAS_330', m: '0010245 - Classic Can Case' },
    { x1: 40, y1: 0, x2: 80, y2: 40, z1: 25, z2: 60, fam: 'LATAS_330', m: '0010245 - Classic Can Case' },
    { x1: 80, y1: 0, x2: 120, y2: 40, z1: 25, z2: 60, fam: 'LATAS_330', m: '0010245 - Classic Can Case' },
  ];
  l2.forEach((b, idx) => {
    boxes.push({
      Box_ID: `DEMO-OK-${200 + idx}`,
      Pallet_ID: 'PALLET_0824_02',
      Layer_ID: 2,
      x_min: b.x1, y_min: b.y1, z_min: b.z1,
      x_max: b.x2, y_max: b.y2, z_max: b.z2,
      material_number: b.m,
      family: b.fam,
      weight: 12.0,
      status: 'PLACED',
      warning: '',
      volume: (b.x2 - b.x1) * (b.y2 - b.y1) * (b.z2 - b.z1)
    });
  });

  // Deliberate Floating Box (No supports underneath!)
  boxes.push({
    Box_ID: `WARN-FLOATING-BOX`,
    Pallet_ID: 'PALLET_0824_02',
    Layer_ID: 3,
    x_min: 10, y_min: 45, z_min: 60,
    x_max: 50, y_max: 75, z_max: 95, // Placed at Z=60 to 95 but area from Y=40 to 80 is empty underneath on Layer 2!
    material_number: '0055110 - Floating Ciel Water 12-Pack',
    family: 'AGUA',
    weight: 12.5,
    status: 'PLACED',
    warning: 'Algorithm placed unit over empty air. Physical stacking impossible without support.',
    volume: 40 * 30 * 35
  });

  // Deliberate Ceiling Violation
  boxes.push({
    Box_ID: `WARN-CEILING-VIOLATION`,
    Pallet_ID: 'PALLET_0824_02',
    Layer_ID: 4,
    x_min: 60, y_min: 20, z_min: 140,
    x_max: 100, y_max: 60, z_max: 176, // Exceeds 165.6cm ceiling limit by 10.4cm
    material_number: '0010108 - Overheight Retornable Case',
    family: 'RETORNABLE',
    weight: 18.2,
    status: 'PLACED',
    warning: 'Total height exceeds vehicle door limit (180cm base included)',
    volume: 40 * 40 * 36
  });

  // Deliberate Failed Placement
  boxes.push({
    Box_ID: `WARN-FAILED-PLACEMENT`,
    Pallet_ID: 'PALLET_0824_02',
    Layer_ID: 5,
    x_min: 0, y_min: 0, z_min: 0,
    x_max: 30, y_max: 20, z_max: 15,
    material_number: '0032991 - Glass Contour Bottle (Could not pack)',
    family: 'VIDRIO',
    weight: 14.0,
    status: 'FAILED',
    warning: 'Placement failed: overlap check error in model heuristic step 4',
    volume: 30 * 20 * 15
  });

  return boxes;
};

const DEFAULT_PALLET_DATA = [...generateMockPallet1(), ...generateMockPallet2()];

// ============================================================================
// Main Application Component
// ============================================================================
export default function App() {
  const [palletData, setPalletData] = useState<Box[]>(DEFAULT_PALLET_DATA);
  const [activePalletId, setActivePalletId] = useState<string>('PALLET_0824_01');
  const [hoveredBox, setHoveredBox] = useState<Box | null>(null);
  const [selectedBox, setSelectedBox] = useState<Box | null>(null);
  
  // Custom Controls
  const [opacity, setOpacity] = useState<number>(0.8);
  const [showWireframes, setShowWireframes] = useState<boolean>(true);
  const [showBoundary, setShowBoundary] = useState<boolean>(true);
  const [showCeilingCage, setShowCeilingCage] = useState<boolean>(true);
  const [selectedLayerFilter, setSelectedLayerFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  
  // 3D Canvas camera parameters
  const [yaw, setYaw] = useState<number>(-0.6); // Radians
  const [pitch, setPitch] = useState<number>(0.6); // Radians
  const [zoom, setZoom] = useState<number>(2.4);
  const [isRotating, setIsRotating] = useState<boolean>(false);
  const [autoRotate, setAutoRotate] = useState<boolean>(false);
  
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragStartRef = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null);
  const requestRef = useRef<number | null>(null);

  // Auto-rotation handling
  useEffect(() => {
    if (autoRotate) {
      const render = () => {
        setYaw(prev => (prev + 0.006) % (Math.PI * 2));
        requestRef.current = requestAnimationFrame(render);
      };
      requestRef.current = requestAnimationFrame(render);
      return () => {
        if (requestRef.current) cancelAnimationFrame(requestRef.current);
      };
    }
  }, [autoRotate]);

  // ============================================================================
  // Excel Spreadsheet Reader Client-side using SheetJS (XLSX)
  // ============================================================================
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target?.result as ArrayBuffer);
        const workbook = XLSX.read(data, { type: 'array' });
        
        // Look for Box_Coordinates sheet (case insensitive)
        const sheetNames = workbook.SheetNames;
        const targetSheetName = sheetNames.find(
          name => name.toLowerCase().replace(/[\s_]+/g, '') === 'boxcoordinates'
        ) || sheetNames[0];

        const worksheet = workbook.Sheets[targetSheetName];
        const rawRows: any[] = XLSX.utils.sheet_to_json(worksheet);

        if (rawRows.length === 0) {
          alert(`No data rows found in sheet "${targetSheetName}". Please verify the structure.`);
          return;
        }

        // Helper function for mapping keys case-insensitively with spaces/underscores stripped
        const findVal = (row: any, ...keys: string[]) => {
          const rowKeys = Object.keys(row);
          for (const k of keys) {
            const cleanTarget = k.toLowerCase().replace(/[\s_]+/g, '');
            const matchedKey = rowKeys.find(
              rk => rk.toLowerCase().replace(/[\s_]+/g, '') === cleanTarget
            );
            if (matchedKey !== undefined) {
              return row[matchedKey];
            }
          }
          return undefined;
        };

        const parsedBoxes: Box[] = rawRows.map((row, idx) => {
          const pallet_id = String(findVal(row, 'Pallet_ID', 'PalletID', 'pallet') || 'PALLET_IMPORTED');
          const layer_id = Number(findVal(row, 'Layer_ID', 'LayerID', 'layer') || 1);
          const box_id = String(findVal(row, 'Box_ID', 'BoxID', 'box', 'id') || `BOX-IMP-${1000 + idx}`);
          
          const x_min = Number(findVal(row, 'x_min', 'xmin', 'x_start') || 0);
          const y_min = Number(findVal(row, 'y_min', 'ymin', 'y_start') || 0);
          const z_min = Number(findVal(row, 'z_min', 'zmin', 'z_start') || 0);
          
          const x_max = Number(findVal(row, 'x_max', 'xmax', 'x_end') || 0);
          const y_max = Number(findVal(row, 'y_max', 'ymax', 'y_end') || 0);
          const z_max = Number(findVal(row, 'z_max', 'zmax', 'z_end') || 0);
          
          const material_number = String(findVal(row, 'Número de material', 'N?mero de material', 'Material_Number', 'Material', 'desc') || 'Standard Beverage Case');
          const family = String(findVal(row, 'Familia_detectada', 'Familia', 'family', 'category') || 'UNKNOWN').toUpperCase();
          const weight = Number(findVal(row, 'Peso_bruto', 'Peso', 'weight', 'gross_weight') || 10.0);
          const status = String(findVal(row, 'Placement_Status', 'status', 'placement') || 'PLACED').toUpperCase();
          const warning = String(findVal(row, 'Placement_Warning', 'warning', 'message') || '');

          return {
            Box_ID: box_id,
            Pallet_ID: pallet_id,
            Layer_ID: layer_id,
            x_min, y_min, z_min,
            x_max, y_max, z_max,
            material_number,
            family,
            weight,
            status,
            warning,
            volume: Math.abs((x_max - x_min) * (y_max - y_min) * (z_max - z_min))
          };
        });

        // Auto-detect and fix swapped X/Y axes (e.g. if exported coordinates have X <= 80 as Width and Y <= 120 as Length)
        let maxX = 0;
        let maxY = 0;
        parsedBoxes.forEach(b => {
          if (b.x_max > maxX) maxX = b.x_max;
          if (b.y_max > maxY) maxY = b.y_max;
        });

        // Standard pallet is 120 (Length / X) x 80 (Width / Y)
        const shouldSwapXY = maxX <= 85 && maxY > 85;
        if (shouldSwapXY) {
          parsedBoxes.forEach(b => {
            const tempMin = b.x_min;
            b.x_min = b.y_min;
            b.y_min = tempMin;

            const tempMax = b.x_max;
            b.x_max = b.y_max;
            b.y_max = tempMax;
          });
        }

        // Update overall state with the parsed boxes
        setPalletData(parsedBoxes);
        
        // Auto-select the first parsed Pallet ID
        const distinctPalletIds = Array.from(new Set(parsedBoxes.map(b => b.Pallet_ID)));
        if (distinctPalletIds.length > 0) {
          setActivePalletId(distinctPalletIds[0]);
        }
        
        setSelectedBox(null);
        setHoveredBox(null);
        alert(`Successfully imported ${parsedBoxes.length} cases from sheet "${targetSheetName}"!`);
      } catch (err: any) {
        alert(`Error parsing Excel file: ${err.message}. Please check columns and format.`);
      }
    };
    reader.readAsArrayBuffer(file);
  };

  const loadSampleExcel = () => {
    // Basic CSV/Excel structure instructions for the user
    const headers = [
      'Pallet_ID', 'Layer_ID', 'Box_ID', 'x_min', 'y_min', 'z_min', 
      'x_max', 'y_max', 'z_max', 'Número de material', 'Familia_detectada', 
      'Peso_bruto', 'Placement_Status', 'Placement_Warning'
    ];
    
    const rows = palletData.map(b => [
      b.Pallet_ID, b.Layer_ID, b.Box_ID, b.x_min, b.y_min, b.z_min,
      b.x_max, b.y_max, b.z_max, b.material_number, b.family,
      b.weight, b.status, b.warning
    ]);

    const worksheet = XLSX.utils.aoa_to_sheet([headers, ...rows]);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Box_Coordinates');
    XLSX.writeFile(workbook, 'ICSO_CocaCola_Heuristics_Coordinates.xlsx');
  };

  // ============================================================================
  // Computations, Validation & Advanced Stability Physics Diagnostics
  // ============================================================================
  
  // Unique pallet IDs list
  const palletIds = useMemo(() => {
    return Array.from(new Set(palletData.map(b => b.Pallet_ID)));
  }, [palletData]);

  // Current active boxes based on pallet ID & optional Layer Filters & Query
  const rawActiveBoxes = useMemo(() => {
    return palletData.filter(b => b.Pallet_ID === activePalletId);
  }, [palletData, activePalletId]);

  // Find minimum Z base of non-failed boxes for active pallet to auto-align wood base
  const minZOfActivePallet = useMemo(() => {
    const placed = rawActiveBoxes.filter(b => b.status !== 'FAILED');
    if (placed.length === 0) return 0;
    const minZ = Math.min(...placed.map(b => b.z_min));
    return minZ >= 10 ? minZ : 0;
  }, [rawActiveBoxes]);

  const activeCeilingLimit = useMemo(() => {
    // If base Z is 0 (mock data), limit of product stack is 165.6 (total 180).
    // If base Z is >= 10 (user CSV including 14.4cm pallet base), limit of product stack is 180.0 (total 180).
    return minZOfActivePallet === 0 ? 165.6 : 180.0;
  }, [minZOfActivePallet]);

  // Calculate high-fidelity physics metrics & custom stability ratings per box
  const processedBoxes = useMemo(() => {
    return rawActiveBoxes.map(box => {
      // Overhang rule: must not exceed pallet footprint bounds
      const hasOverhang = box.x_min < 0 || box.x_max > PALLET_WIDTH || box.y_min < 0 || box.y_max > PALLET_DEPTH;
      
      // Ceiling check
      const exceedsCeiling = box.z_max > activeCeilingLimit;

      // Coordinate anomalies
      const hasInvalidCoords = box.x_min >= box.x_max || box.y_min >= box.y_max || box.z_min >= box.z_max;

      // Floating support checking: 
      // If box is directly on ground (z_min == minZOfActivePallet), it is perfectly supported.
      // Otherwise, check what percentage of its bottom area overlaps with top faces of boxes directly underneath.
      let isFloating = false;
      if (box.z_min > minZOfActivePallet && box.status !== 'FAILED') {
        const boxBaseArea = (box.x_max - box.x_min) * (box.y_max - box.y_min);
        let supportArea = 0;

        // Scan all other boxes in the same pallet
        rawActiveBoxes.forEach(other => {
          if (other.Box_ID === box.Box_ID || other.status === 'FAILED') return;
          
          // Must touch or nearly touch vertically (within 1cm allowance for model tolerances)
          const verticalTouch = Math.abs(other.z_max - box.z_min) <= 1.0;
          if (verticalTouch) {
            // Find intersection in X-Y plane
            const xOverlap = Math.max(0, Math.min(box.x_max, other.x_max) - Math.max(box.x_min, other.x_min));
            const yOverlap = Math.max(0, Math.min(box.y_max, other.y_max) - Math.max(box.y_min, other.y_min));
            supportArea += (xOverlap * yOverlap);
          }
        });

        // If support area is less than 30% of its total base area, trigger stability alert
        isFloating = supportArea < (boxBaseArea * 0.3);
      }

      return {
        ...box,
        hasOverhang,
        exceedsCeiling,
        hasInvalidCoords,
        isFloating
      };
    });
  }, [rawActiveBoxes, minZOfActivePallet, activeCeilingLimit]);

  // Apply visual filtering (Layer + Search query)
  const filteredBoxes = useMemo(() => {
    return processedBoxes.filter(box => {
      // 1. Filter by Layer Selection
      if (selectedLayerFilter !== 'ALL') {
        if (selectedLayerFilter.startsWith('UP_TO_')) {
          const maxLayer = parseInt(selectedLayerFilter.replace('UP_TO_', ''));
          if (box.Layer_ID > maxLayer) return false;
        } else {
          const exactLayer = parseInt(selectedLayerFilter);
          if (box.Layer_ID !== exactLayer) return false;
        }
      }

      // 2. Filter by search query (box ID, family, or material number)
      if (searchQuery.trim() !== '') {
        const q = searchQuery.toLowerCase();
        return (
          box.Box_ID.toLowerCase().includes(q) ||
          box.family.toLowerCase().includes(q) ||
          box.material_number.toLowerCase().includes(q)
        );
      }

      return true;
    });
  }, [processedBoxes, selectedLayerFilter, searchQuery]);

  // Aggregate stats
  const palletSummary = useMemo((): PalletSummary => {
    const placed = processedBoxes.filter(b => b.status !== 'FAILED');
    const failed = processedBoxes.filter(b => b.status === 'FAILED');
    const maxHeight = placed.length > 0 ? Math.max(...placed.map(b => b.z_max)) : 0;
    const totalVolume = placed.reduce((sum, b) => sum + b.volume, 0);
    const totalWeight = placed.reduce((sum, b) => sum + b.weight, 0);

    // Utilization calculation based on cubic fit inside bounding height
    const containerVolume = PALLET_WIDTH * PALLET_DEPTH * (maxHeight || activeCeilingLimit);
    const utilization = containerVolume > 0 ? Math.min(100, (totalVolume / containerVolume) * 100) : 0;

    const overhangCount = processedBoxes.filter(b => b.hasOverhang && b.status !== 'FAILED').length;
    const ceilingCount = processedBoxes.filter(b => b.exceedsCeiling && b.status !== 'FAILED').length;
    const floatingCount = processedBoxes.filter(b => b.isFloating).length;

    return {
      palletId: activePalletId,
      totalBoxes: processedBoxes.length,
      placedBoxes: placed.length,
      failedBoxes: failed.length,
      maxHeight,
      totalVolume,
      utilization,
      totalWeight,
      overhangCount,
      ceilingCount,
      floatingCount
    };
  }, [processedBoxes, activePalletId, activeCeilingLimit]);

  // Available layers list
  const availableLayers = useMemo(() => {
    return Array.from(new Set(processedBoxes.map(b => b.Layer_ID))).sort((a, b) => a - b);
  }, [processedBoxes]);

  // Distribution chart of products
  const productDistribution = useMemo(() => {
    const counts: { [key: string]: number } = {};
    processedBoxes.forEach(b => {
      const fam = b.status === 'FAILED' ? 'FAILED' : (b.family || 'UNKNOWN');
      counts[fam] = (counts[fam] || 0) + 1;
    });
    return Object.entries(counts).map(([name, count]) => ({ name, count }));
  }, [processedBoxes]);

  // ============================================================================
  // Canvas-based 3D Projection Engine Rendering with Hover & Select Detect
  // ============================================================================
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set high-DPI scaling
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const width = rect.width;
    const height = rect.height;
    const cx = width / 2;
    const cy = height / 1.7; // shift slightly downwards to make space for taller stacking

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Simple Point 3D to 2D projection
    const project = (x: number, y: number, z: number) => {
      // Shift coordinate origin to center of pallet base
      const rx = x - PALLET_WIDTH / 2;
      const ry = y - PALLET_DEPTH / 2;
      const rz = z - activeCeilingLimit / 3; // base alignment adjustment

      // 1. Yaw rotation (about Z-axis)
      const x1 = rx * Math.cos(yaw) - ry * Math.sin(yaw);
      const y1 = rx * Math.sin(yaw) + ry * Math.cos(yaw);
      const z1 = rz;

      // 2. Pitch rotation (about X-axis)
      const x2 = x1;
      const y2 = y1 * Math.cos(pitch) - z1 * Math.sin(pitch);
      const z2 = y1 * Math.sin(pitch) + z1 * Math.cos(pitch);

      return {
        x: cx + x2 * zoom,
        y: cy - z2 * zoom,
        depth: y2 // larger depth means further into screen, smaller depth means closer to viewport
      };
    };

    // Helper to draw a solid 3D box or cage
    const draw3DBox = (
      xMin: number, yMin: number, zMin: number,
      xMax: number, yMax: number, zMax: number,
      colors: { fill: string; stroke: string },
      drawWire: boolean,
      isSolid = true,
      lineWidth = 1
    ) => {
      // Compute 8 corners of the box
      const p1 = project(xMin, yMin, zMin); // Back-Bottom-Left
      const p2 = project(xMax, yMin, zMin); // Back-Bottom-Right
      const p3 = project(xMax, yMax, zMin); // Front-Bottom-Right
      const p4 = project(xMin, yMax, zMin); // Front-Bottom-Left
      
      const p5 = project(xMin, yMin, zMax); // Back-Top-Left
      const p6 = project(xMax, yMin, zMax); // Back-Top-Right
      const p7 = project(xMax, yMax, zMax); // Front-Top-Right
      const p8 = project(xMin, yMax, zMax); // Front-Top-Left

      // Define 6 faces with their vertices and center depths
      const faces = [
        { points: [p1, p2, p3, p4], name: 'bottom', depth: (p1.depth + p2.depth + p3.depth + p4.depth) / 4 },
        { points: [p5, p6, p7, p8], name: 'top', depth: (p5.depth + p6.depth + p7.depth + p8.depth) / 4 },
        { points: [p1, p2, p6, p5], name: 'back', depth: (p1.depth + p2.depth + p6.depth + p5.depth) / 4 },
        { points: [p3, p4, p8, p7], name: 'front', depth: (p3.depth + p4.depth + p8.depth + p7.depth) / 4 },
        { points: [p1, p4, p8, p5], name: 'left', depth: (p1.depth + p4.depth + p8.depth + p5.depth) / 4 },
        { points: [p2, p3, p7, p6], name: 'right', depth: (p2.depth + p3.depth + p7.depth + p6.depth) / 4 },
      ];

      // Sort faces back-to-front ( Painter's algorithm within a single box )
      faces.sort((a, b) => b.depth - a.depth);

      faces.forEach(f => {
        ctx.beginPath();
        ctx.moveTo(f.points[0].x, f.points[0].y);
        for (let i = 1; i < 4; i++) {
          ctx.lineTo(f.points[i].x, f.points[i].y);
        }
        ctx.closePath();

        if (isSolid) {
          ctx.fillStyle = colors.fill;
          ctx.fill();

          // ALWAYS draw a subtle dark border around solid faces to prevent adjacent boxes/faces blending together!
          ctx.strokeStyle = 'rgba(15, 23, 42, 0.45)';
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }
        
        if (drawWire) {
          // Draw a slightly thicker black outline first to separate adjacent boxes clearly
          ctx.strokeStyle = '#000000';
          ctx.lineWidth = lineWidth + 1.5;
          ctx.stroke();

          // Draw the colorful inner stroke
          ctx.strokeStyle = colors.stroke;
          ctx.lineWidth = lineWidth;
          ctx.stroke();
        }
      });
    };



    // --- 1. DRAW WOOD PALLET BASE ---
    // Standard size 120 x 80 x 14.4 cm to match exact physical MADERA_CM
    const baseZ = minZOfActivePallet; // can be 0 or 14.4
    const deckMin = baseZ - 4.4;
    const deckMax = baseZ;
    const feetMin = baseZ - 14.4;
    const feetMax = baseZ - 4.4;

    draw3DBox(
      0, 0, deckMin,
      PALLET_WIDTH, PALLET_DEPTH, deckMax,
      { fill: 'rgba(180, 120, 70, 0.95)', stroke: '#442200' }, // rich, warm wood color
      true,
      true,
      1.8 // thicker, clearer lines!
    );

    // Draw pallet feet blocks
    const woodFeet = [
      { x1: 0, y1: 0 }, { x1: 50, y1: 0 }, { x1: 100, y1: 0 },
      { x1: 0, y1: 35 }, { x1: 50, y1: 35 }, { x1: 100, y1: 35 },
      { x1: 0, y1: 70 }, { x1: 50, y1: 70 }, { x1: 100, y1: 70 }
    ];
    woodFeet.forEach(f => {
      draw3DBox(
        f.x1, f.y1, feetMin,
        Math.min(f.x1 + 20, PALLET_WIDTH), Math.min(f.y1 + 10, PALLET_DEPTH), feetMax,
        { fill: 'rgba(150, 95, 50, 0.95)', stroke: '#2e1400' }, // rich warm dark wood feet
        true,
        true,
        1.5
      );
    });

    // --- 2. DRAW PALLET BOUNDARY WIRE CAGE (If active) ---
    if (showBoundary) {
      draw3DBox(
        0, 0, minZOfActivePallet,
        PALLET_WIDTH, PALLET_DEPTH, activeCeilingLimit,
        { fill: 'rgba(0, 0, 0, 0)', stroke: 'rgba(45, 212, 191, 0.45)' }, // more visible outline
        true,
        false, // wire only
        1.5 // thicker lines
      );
    }

    // --- 3. DRAW CEILING LIMIT CAGE (If active) ---
    if (showCeilingCage) {
      draw3DBox(
        0, 0, activeCeilingLimit,
        PALLET_WIDTH, PALLET_DEPTH, activeCeilingLimit + 2,
        { fill: 'rgba(239, 68, 68, 0.15)', stroke: 'rgba(239, 68, 68, 0.7)' }, // more visible red ceiling plate
        true,
        true,
        1.5
      );
    }

    // --- 4. RENDER PLACED BOXES WITH Painter's Algorithm ---
    // Compute depth for every box to sort them
    const boxesWithDepth = filteredBoxes
      .filter(b => b.status !== 'FAILED')
      .map(box => {
        // Center coordinates
        const mx = (box.x_min + box.x_max) / 2;
        const my = (box.y_min + box.y_max) / 2;
        const mz = (box.z_min + box.z_max) / 2;
        const projected = project(mx, my, mz);
        return { box, depth: projected.depth };
      });

    // Sort by depth descending (furthest first, closest last)
    boxesWithDepth.sort((a, b) => b.depth - a.depth);

    boxesWithDepth.forEach(({ box }) => {
      const isSelected = selectedBox?.Box_ID === box.Box_ID;
      const isHovered = hoveredBox?.Box_ID === box.Box_ID;

      // Base style from product family
      const scheme = FAMILY_COLORS[box.family] || FAMILY_COLORS['UNKNOWN'];
      
      let fillColor = scheme.fill;
      let strokeColor = scheme.stroke;
      let strokeWidth = 1.0;

      // Highlight effects
      if (isSelected) {
        fillColor = 'rgba(45, 212, 191, 0.9)'; // Bright Teal
        strokeColor = '#00f2fe';
        strokeWidth = 2.5;
      } else if (isHovered) {
        fillColor = 'rgba(255, 255, 255, 0.8)'; // bright semi-trans white
        strokeColor = '#ffffff';
        strokeWidth = 2.0;
      } else if (box.isFloating) {
        fillColor = 'rgba(251, 191, 36, 0.5)'; // Amber instability color
        strokeColor = '#fbbf24';
        strokeWidth = 1.8;
      } else if (box.hasOverhang) {
        fillColor = 'rgba(244, 63, 94, 0.6)'; // Rosy alert
        strokeColor = '#f43f5e';
        strokeWidth = 1.8;
      }

      // Respect transparency slider
      if (!isSelected && !isHovered) {
        const match = fillColor.match(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/);
        if (match) {
          fillColor = `rgba(${match[1]}, ${match[2]}, ${match[3]}, ${parseFloat(match[4]) * opacity})`;
        }
      }

      // Draw the box sized exactly to the L*W*H real dimensions of the case
      draw3DBox(
        box.x_min, box.y_min, box.z_min,
        box.x_max, box.y_max, box.z_max,
        { fill: fillColor, stroke: strokeColor },
        showWireframes || isSelected || isHovered,
        true,
        strokeWidth
      );

      // Support vectors: If selected, draw anchor lines to ground
      if (isSelected && box.z_min > 0) {
        // Draw dashed drop shadow vector down to ground
        ctx.beginPath();
        const bottomCenter = project((box.x_min + box.x_max) / 2, (box.y_min + box.y_max) / 2, box.z_min);
        const groundCenter = project((box.x_min + box.x_max) / 2, (box.y_min + box.y_max) / 2, 0);
        ctx.moveTo(bottomCenter.x, bottomCenter.y);
        ctx.lineTo(groundCenter.x, groundCenter.y);
        ctx.strokeStyle = '#2dd4bf';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]); // reset
      }
    });

  }, [filteredBoxes, yaw, pitch, zoom, opacity, showWireframes, showBoundary, showCeilingCage, hoveredBox, selectedBox]);

  // ============================================================================
  // Interactive Controls & Handlers
  // ============================================================================
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    setIsRotating(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      yaw: yaw,
      pitch: pitch
    };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isRotating || !dragStartRef.current) {
      // Handle Mouse Hover Detection (Hit Testing)
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // Project all boxes and find the top-most under the cursor
      // We process in back-to-front drawer order, meaning the last matched box in depth order is the top-most
      let found: Box | null = null;

      // We'll project the base centers of boxes to find closest coordinates
      const cx = rect.width / 2;
      const cy = rect.height / 1.7;

      const projectPoint = (x: number, y: number, z: number) => {
        const rx = x - PALLET_WIDTH / 2;
        const ry = y - PALLET_DEPTH / 2;
        const rz = z - CEILING_LIMIT / 3;
        const x1 = rx * Math.cos(yaw) - ry * Math.sin(yaw);
        const y1 = rx * Math.sin(yaw) + ry * Math.cos(yaw);
        const z1 = rz;
        const x2 = x1;
        const y2 = y1 * Math.cos(pitch) - z1 * Math.sin(pitch);
        const z2 = y1 * Math.sin(pitch) + z1 * Math.cos(pitch);
        return { x: cx + x2 * zoom, y: cy - z2 * zoom, depth: y2 };
      };

      // Helper for point-in-polygon algorithm (for quadrilaterals)
      const isPointInQuad = (px: number, py: number, q: any[]) => {
        let inside = false;
        for (let i = 0, j = q.length - 1; i < q.length; j = i++) {
          const xi = q[i].x, yi = q[i].y;
          const xj = q[j].x, yj = q[j].y;
          const intersect = ((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
          if (intersect) inside = !inside;
        }
        return inside;
      };

      // Sort boxes by depth so we match the top-most box under cursor last
      const sortedBoxes = [...filteredBoxes]
        .filter(b => b.status !== 'FAILED')
        .map(b => {
          const projected = projectPoint((b.x_min + b.x_max) / 2, (b.y_min + b.y_max) / 2, (b.z_min + b.z_max) / 2);
          return { b, depth: projected.depth };
        })
        .sort((a, b) => b.depth - a.depth); // furthest first

      sortedBoxes.forEach(({ b }) => {
        // Project 8 corners and build visible faces
        // To simplify, check if the mouse is in the projected 2D boundary of the box
        const corners = [
          projectPoint(b.x_min, b.y_min, b.z_min),
          projectPoint(b.x_max, b.y_min, b.z_min),
          projectPoint(b.x_max, b.y_max, b.z_min),
          projectPoint(b.x_min, b.y_max, b.z_min),
          projectPoint(b.x_min, b.y_min, b.z_max),
          projectPoint(b.x_max, b.y_min, b.z_max),
          projectPoint(b.x_max, b.y_max, b.z_max),
          projectPoint(b.x_min, b.y_max, b.z_max),
        ];

        // Let's check 3 primary visible faces (top, front, right)
        const topFace = [corners[4], corners[5], corners[6], corners[7]];
        const frontFace = [corners[3], corners[2], corners[6], corners[7]];
        const rightFace = [corners[1], corners[2], corners[6], corners[5]];

        if (isPointInQuad(mouseX, mouseY, topFace) || 
            isPointInQuad(mouseX, mouseY, frontFace) || 
            isPointInQuad(mouseX, mouseY, rightFace)) {
          found = b;
        }
      });

      setHoveredBox(found);
      return;
    }

    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;

    // Apply sensitivity mapping
    setYaw(dragStartRef.current.yaw + dx * 0.008);
    setPitch(Math.max(-Math.PI/2.1, Math.min(Math.PI/2.1, dragStartRef.current.pitch + dy * 0.008)));
  };

  const handleMouseUp = () => {
    setIsRotating(false);
    dragStartRef.current = null;
  };

  const handleCanvasClick = () => {
    if (hoveredBox) {
      setSelectedBox(hoveredBox);
    } else {
      setSelectedBox(null);
    }
  };

  // Touch handlers for mobile/tablet optimization
  const handleTouchStart = (e: React.TouchEvent<HTMLCanvasElement>) => {
    if (e.touches.length === 1) {
      setIsRotating(true);
      dragStartRef.current = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
        yaw: yaw,
        pitch: pitch
      };
    }
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLCanvasElement>) => {
    if (!isRotating || !dragStartRef.current || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - dragStartRef.current.x;
    const dy = e.touches[0].clientY - dragStartRef.current.y;
    setYaw(dragStartRef.current.yaw + dx * 0.01);
    setPitch(Math.max(-Math.PI/2, Math.min(Math.PI/2, dragStartRef.current.pitch + dy * 0.01)));
  };

  // Zoom Helpers
  const zoomIn = () => setZoom(prev => Math.min(5, prev + 0.3));
  const zoomOut = () => setZoom(prev => Math.max(0.8, prev - 0.3));
  const resetView = () => {
    setYaw(-0.6);
    setPitch(0.6);
    setZoom(2.4);
    setAutoRotate(false);
    setSelectedBox(null);
  };

  // Quick preset layers helper
  const handleLayerPreset = (preset: string) => {
    setSelectedLayerFilter(preset);
  };

  // List of active warnings
  const warningsList = useMemo(() => {
    const list: { id: string; boxId: string; type: 'overhang' | 'ceiling' | 'floating' | 'failed'; message: string; boxRef: Box }[] = [];
    processedBoxes.forEach(b => {
      if (b.status === 'FAILED') {
        list.push({
          id: `fail-${b.Box_ID}`,
          boxId: b.Box_ID,
          type: 'failed',
          message: `Heuristic Placement Failed: ${b.material_number || b.warning}`,
          boxRef: b
        });
      }
      if (b.hasOverhang && b.status !== 'FAILED') {
        list.push({
          id: `over-${b.Box_ID}`,
          boxId: b.Box_ID,
          type: 'overhang',
          message: `Base Footprint Overhang: x[${b.x_min}-${b.x_max}] y[${b.y_min}-${b.y_max}] exceeds 120x80cm`,
          boxRef: b
        });
      }
      if (b.exceedsCeiling && b.status !== 'FAILED') {
        list.push({
          id: `ceil-${b.Box_ID}`,
          boxId: b.Box_ID,
          type: 'ceiling',
          message: `Ceiling Door Height Violation: Box top Z is ${b.z_max} cm (Max allowable is ${CEILING_LIMIT} cm)`,
          boxRef: b
        });
      }
      if (b.isFloating) {
        list.push({
          id: `float-${b.Box_ID}`,
          boxId: b.Box_ID,
          type: 'floating',
          message: `Gravity Instability Alert: Case is floating or has inadequate vertical support beneath it`,
          boxRef: b
        });
      }
    });
    return list;
  }, [processedBoxes]);

  return (
    <div className="min-h-screen bg-[#0f172a] text-[#f8fafc] font-sans antialiased flex flex-col">
      
      {/* ========================================== HEADER ========================================== */}
      <header className="bg-[#1e293b] border-b border-[#334155] px-6 py-4 flex flex-col md:flex-row items-center justify-between gap-4 shrink-0 shadow-lg">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl md:text-2xl font-bold font-display tracking-tight text-[#f8fafc]">
              ICSO Pallet Optimization <span className="text-[#e41e2b]">3D Visualizer</span>
            </h1>
            <span className="bg-[#e41e2b]/10 border border-[#e41e2b]/30 text-[#e41e2b] px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider">
              V2.5 Heuristic
            </span>
          </div>
          <p className="text-xs text-[#94a3b8] mt-1 font-medium">
            University Capstone Project Diagnostics Sandbox & Operational Stacking Analyzer
          </p>
        </div>

        {/* Actions bar */}
        <div className="flex items-center flex-wrap gap-2.5">
          <button 
            id="btn-export"
            onClick={loadSampleExcel}
            className="px-3 py-1.5 bg-[#334155] hover:bg-[#475569] border border-[#475569] hover:border-[#2dd4bf] text-xs font-semibold rounded transition flex items-center gap-1.5 text-white shadow-sm cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-[#2dd4bf]" />
            Export Current to Excel
          </button>
          
          <label 
            id="btn-upload"
            className="px-3.5 py-1.5 bg-[#e41e2b] hover:bg-[#b91c1c] text-xs font-bold rounded transition flex items-center gap-1.5 text-white shadow-sm cursor-pointer"
          >
            <Upload className="w-3.5 h-3.5" />
            Upload Optimization Sheet
            <input 
              type="file" 
              accept=".xlsx, .xls, .csv" 
              onChange={handleFileUpload} 
              className="hidden" 
            />
          </label>
        </div>
      </header>

      {/* ========================================== STATS BAR ========================================== */}
      <section className="bg-[#0f172a] px-6 py-4 border-b border-[#1e293b] grid grid-cols-2 md:grid-cols-5 gap-3 shrink-0">
        
        {/* Metric Card: Total cases */}
        <div id="stat-total-cases" className="bg-[#1e293b] border border-[#334155] rounded-lg p-3.5 flex flex-col justify-center">
          <span className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wider block">Total Boxes</span>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-2xl font-bold font-display text-white">{palletSummary.totalBoxes}</span>
            <span className="text-xs text-[#94a3b8]">units</span>
          </div>
          <span className="text-[10px] text-[#2dd4bf] font-semibold mt-0.5 block">
            {palletSummary.placedBoxes} placed | {palletSummary.failedBoxes} failed
          </span>
        </div>

        {/* Metric Card: Max height */}
        <div id="stat-max-height" className="bg-[#1e293b] border border-[#334155] rounded-lg p-3.5 flex flex-col justify-center">
          <span className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wider block">Pallet Height</span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className="text-2xl font-bold font-display text-white">{palletSummary.maxHeight.toFixed(1)}</span>
            <span className="text-xs text-[#2dd4bf]">/ {activeCeilingLimit.toFixed(1)} cm</span>
          </div>
          {palletSummary.maxHeight > activeCeilingLimit ? (
            <span className="text-[10px] text-[#ef4444] font-semibold mt-0.5 flex items-center gap-0.5">
              <AlertTriangle className="w-3 h-3" /> Height Limit Exceeded
            </span>
          ) : (
            <span className="text-[10px] text-[#34d399] font-semibold mt-0.5 block">✓ Inside Ceiling Limit</span>
          )}
        </div>

        {/* Metric Card: Volume packing density */}
        <div id="stat-packing-utilization" className="bg-[#1e293b] border border-[#334155] rounded-lg p-3.5 flex flex-col justify-center">
          <span className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wider block">Packing Utilization</span>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-2xl font-bold font-display text-white">{palletSummary.utilization.toFixed(1)}%</span>
            <span className="text-xs text-[#94a3b8]">volumetric</span>
          </div>
          <span className="text-[10px] text-[#94a3b8] font-semibold mt-0.5 block">
            {(palletSummary.totalVolume / 1000).toFixed(1)}K cm³ product volume
          </span>
        </div>

        {/* Metric Card: Total weight */}
        <div id="stat-gross-weight" className="bg-[#1e293b] border border-[#334155] rounded-lg p-3.5 flex flex-col justify-center">
          <span className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wider block">Gross Weight</span>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-2xl font-bold font-display text-white">{palletSummary.totalWeight.toFixed(1)}</span>
            <span className="text-xs text-[#94a3b8]">kg</span>
          </div>
          <span className="text-[10px] text-[#34d399] font-semibold mt-0.5 block flex items-center gap-0.5">
            <Scale className="w-3 h-3 text-[#2dd4bf]" /> Ideal center-of-gravity center
          </span>
        </div>

        {/* Metric Card: Active warnings alerts status */}
        <div id="stat-warning-count" className={`border rounded-lg p-3.5 flex flex-col justify-center transition-all ${
          warningsList.length > 0 
            ? 'bg-[#ef4444]/5 border-[#ef4444]/30 text-white' 
            : 'bg-[#10b981]/5 border-[#10b981]/30 text-white'
        }`}>
          <span className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wider block">Diagnostics Status</span>
          <div className="flex items-center gap-2 mt-1">
            {warningsList.length > 0 ? (
              <>
                <AlertTriangle className="w-6 h-6 text-[#ef4444]" />
                <span className="text-2xl font-bold font-display">{warningsList.length} Warnings</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-6 h-6 text-[#10b981]" />
                <span className="text-2xl font-bold font-display">Stable Stack</span>
              </>
            )}
          </div>
          <span className="text-[10px] text-[#94a3b8] font-semibold mt-0.5 block">
            {palletSummary.overhangCount} Overhang | {palletSummary.floatingCount} Gravity Alert
          </span>
        </div>

      </section>

      {/* ========================================== MAIN LAYOUT GRID ========================================== */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 overflow-hidden">
        
        {/* ================================== LEFT SIDEBAR: CONTROLS (3 columns) ================================== */}
        <aside id="left-sidebar-controls" className="lg:col-span-3 bg-[#1e293b] border-r border-[#334155] p-5 flex flex-col gap-6 overflow-y-auto">
          
          {/* Active Pallet switcher */}
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-[#2dd4bf] uppercase tracking-widest block">Active Pallet ID</label>
            <select 
              id="pallet-select"
              value={activePalletId}
              onChange={(e) => {
                setActivePalletId(e.target.value);
                setSelectedBox(null);
              }}
              className="w-full bg-[#0f172a] border border-[#334155] text-white px-3 py-2 rounded text-sm font-semibold focus:outline-none focus:ring-1 focus:ring-[#2dd4bf] cursor-pointer"
            >
              {palletIds.map(id => {
                const count = palletData.filter(b => b.Pallet_ID === id).length;
                return (
                  <option key={id} value={id}>
                    {id} ({count} Cases)
                  </option>
                );
              })}
            </select>
          </div>

          {/* Quick instructions on coordinate structure */}
          <div className="bg-[#0f172a] border border-[#334155] rounded-lg p-3 text-[11px] leading-relaxed text-[#94a3b8] space-y-1">
            <span className="font-bold text-[#f8fafc] flex items-center gap-1">
              <Info className="w-3.5 h-3.5 text-[#2dd4bf]" /> Expected Sheet Structure
            </span>
            <p>Upload a workbook with a sheet named <code className="text-[#2dd4bf] text-[10px]">Box_Coordinates</code>.</p>
            <p>Requires box dimension ranges: <code className="text-[#94a3b8]">x_min, x_max, y_min, y_max, z_min, z_max</code> (in cm).</p>
          </div>

          {/* Visual controls */}
          <div className="space-y-4">
            <h3 className="text-xs font-bold text-[#2dd4bf] uppercase tracking-widest border-b border-[#334155] pb-1.5 flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5" /> Visualization Parameters
            </h3>

            {/* Opacity slider */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-[#94a3b8] font-medium">Box Opacity</span>
                <span className="text-white font-mono font-bold">{(opacity * 100).toFixed(0)}%</span>
              </div>
              <input 
                id="opacity-slider"
                type="range" 
                min="0.1" 
                max="1.0" 
                step="0.05"
                value={opacity} 
                onChange={(e) => setOpacity(parseFloat(e.target.value))}
                className="w-full accent-[#2dd4bf] bg-[#0f172a] h-1.5 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {/* Checkboxes */}
            <div className="space-y-2.5 pt-2">
              <label id="toggle-wireframe" className="flex items-center gap-2.5 text-xs text-[#94a3b8] hover:text-white cursor-pointer select-none">
                <input 
                  type="checkbox" 
                  checked={showWireframes} 
                  onChange={(e) => setShowWireframes(e.target.checked)}
                  className="rounded bg-[#0f172a] border-[#334155] text-[#2dd4bf] focus:ring-0 focus:ring-offset-0 w-4 h-4"
                />
                Show Case Wireframe Lines
              </label>

              <label id="toggle-boundary" className="flex items-center gap-2.5 text-xs text-[#94a3b8] hover:text-white cursor-pointer select-none">
                <input 
                  type="checkbox" 
                  checked={showBoundary} 
                  onChange={(e) => setShowBoundary(e.target.checked)}
                  className="rounded bg-[#0f172a] border-[#334155] text-[#2dd4bf] focus:ring-0 focus:ring-offset-0 w-4 h-4"
                />
                Show Pallet Floor Bound (120x80)
              </label>

              <label id="toggle-ceiling" className="flex items-center gap-2.5 text-xs text-[#94a3b8] hover:text-white cursor-pointer select-none">
                <input 
                  type="checkbox" 
                  checked={showCeilingCage} 
                  onChange={(e) => setShowCeilingCage(e.target.checked)}
                  className="rounded bg-[#0f172a] border-[#334155] text-[#2dd4bf] focus:ring-0 focus:ring-offset-0 w-4 h-4"
                />
                Show Ceiling Plane Limit ({activeCeilingLimit.toFixed(1)}cm)
              </label>
            </div>
          </div>

          {/* Stacking layer filters */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-[#2dd4bf] uppercase tracking-widest border-b border-[#334155] pb-1.5 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" /> Filter by Layer height
            </h3>

            {/* List selector of presets */}
            <div className="grid grid-cols-4 gap-1.5">
              <button 
                id="btn-layer-all"
                onClick={() => handleLayerPreset('ALL')}
                className={`py-1.5 rounded text-xs font-bold transition cursor-pointer ${
                  selectedLayerFilter === 'ALL' 
                    ? 'bg-[#e41e2b] text-white' 
                    : 'bg-[#0f172a] text-[#94a3b8] hover:bg-[#334155]'
                }`}
              >
                ALL
              </button>
              {availableLayers.map(l => (
                <button 
                  id={`btn-layer-${l}`}
                  key={l}
                  onClick={() => handleLayerPreset(String(l))}
                  className={`py-1.5 rounded text-xs font-mono font-bold transition cursor-pointer ${
                    selectedLayerFilter === String(l) 
                      ? 'bg-[#2dd4bf] text-[#0f172a]' 
                      : 'bg-[#0f172a] text-[#94a3b8] hover:bg-[#334155]'
                  }`}
                >
                  L{l}
                </button>
              ))}
            </div>

            {/* Slider range filters */}
            <div className="space-y-1 pt-1.5">
              <span className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wide block">Incremental build:</span>
              <div className="grid grid-cols-3 gap-1.5">
                {(availableLayers.length > 0 ? availableLayers : [1]).map(max => (
                  <button
                    id={`btn-build-up-to-${max}`}
                    key={max}
                    onClick={() => handleLayerPreset(`UP_TO_${max}`)}
                    className={`py-1 px-1 rounded text-[10px] font-semibold transition cursor-pointer text-center ${
                      selectedLayerFilter === `UP_TO_${max}` 
                        ? 'bg-[#3b82f6] text-white font-bold' 
                        : 'bg-[#0f172a] text-[#94a3b8] hover:bg-[#334155]'
                    }`}
                  >
                    Up to L{max}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Search filter for boxes */}
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-widest block">Search Case ID / Family</label>
            <div className="relative">
              <input 
                id="search-input"
                type="text" 
                placeholder="e.g. LATAS_330, CC-201"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#0f172a] border border-[#334155] text-white rounded px-3 py-1.5 pl-8 text-xs focus:outline-none focus:ring-1 focus:ring-[#2dd4bf]"
              />
              <Search className="w-3.5 h-3.5 text-[#94a3b8] absolute left-2.5 top-2.5" />
            </div>
          </div>

          {/* Diagnostics Sandbox info */}
          <div className="mt-auto pt-6 border-t border-[#334155] text-center">
            <span className="text-[10px] text-[#94a3b8] block">Pre-loaded sandbox cases:</span>
            <div className="flex justify-center gap-2 mt-2">
              <button 
                id="btn-sandbox-1"
                onClick={() => {
                  setPalletData(DEFAULT_PALLET_DATA);
                  setActivePalletId('PALLET_0824_01');
                  setSelectedBox(null);
                }}
                className="px-2 py-1 bg-[#334155] hover:bg-[#475569] text-[9px] font-bold rounded text-white transition cursor-pointer"
              >
                Pallet 1 (Ideal Stack)
              </button>
              <button 
                id="btn-sandbox-2"
                onClick={() => {
                  setPalletData(DEFAULT_PALLET_DATA);
                  setActivePalletId('PALLET_0824_02');
                  setSelectedBox(null);
                }}
                className="px-2 py-1 bg-[#334155] hover:bg-[#475569] text-[9px] font-bold rounded text-white transition cursor-pointer"
              >
                Pallet 2 (Warnings Demo)
              </button>
            </div>
          </div>

        </aside>

        {/* ================================== CENTER PANEL: 3D INTERACTIVE CANVAS (6 columns) ================================== */}
        <main className="lg:col-span-6 bg-[#0f172a] relative flex flex-col border-r border-[#334155]">
          
          {/* Instructions Overlay */}
          <div className="absolute top-4 left-4 z-10 pointer-events-none">
            <div className="bg-[#1e293b]/90 border border-[#334155]/80 backdrop-blur-sm px-3 py-2 rounded shadow-lg text-[11px] text-[#94a3b8] space-y-0.5">
              <span className="text-[#f8fafc] font-bold block flex items-center gap-1">
                <Compass className="w-3.5 h-3.5 text-[#2dd4bf]" /> Navigation Instructions
              </span>
              <p>• <span className="text-white font-medium">Click + Drag</span> to rotate view</p>
              <p>• <span className="text-white font-medium">Hover/Click</span> case to inspect physics</p>
              <p>• <span className="text-white font-medium">Pinch/Scroll</span> to zoom in/out</p>
            </div>
          </div>

          {/* Quick interactive viewport action bar overlay */}
          <div className="absolute top-4 right-4 z-10 flex gap-1 bg-[#1e293b]/90 border border-[#334155]/80 backdrop-blur-sm p-1 rounded shadow-lg">
            <button 
              id="btn-cam-left"
              onClick={() => setYaw(prev => prev - 0.25)} 
              title="Rotate Left"
              className="p-1.5 hover:bg-[#334155] rounded text-[#94a3b8] hover:text-white transition cursor-pointer"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button 
              id="btn-cam-right"
              onClick={() => setYaw(prev => prev + 0.25)} 
              title="Rotate Right"
              className="p-1.5 hover:bg-[#334155] rounded text-[#94a3b8] hover:text-white transition cursor-pointer"
            >
              <RotateCw className="w-4 h-4" />
            </button>
            <div className="w-[1px] bg-[#334155] mx-1"></div>
            <button 
              id="btn-zoom-in"
              onClick={zoomIn} 
              title="Zoom In"
              className="p-1.5 hover:bg-[#334155] rounded text-[#94a3b8] hover:text-white transition cursor-pointer"
            >
              <Maximize2 className="w-4 h-4" />
            </button>
            <button 
              id="btn-zoom-out"
              onClick={zoomOut} 
              title="Zoom Out"
              className="p-1.5 hover:bg-[#334155] rounded text-[#94a3b8] hover:text-white transition cursor-pointer"
            >
              <Minimize2 className="w-4 h-4" />
            </button>
            <div className="w-[1px] bg-[#334155] mx-1"></div>
            <button 
              id="btn-auto-rotate"
              onClick={() => setAutoRotate(prev => !prev)} 
              title="Toggle Auto Rotation"
              className={`p-1.5 rounded transition cursor-pointer ${autoRotate ? 'bg-[#2dd4bf]/20 text-[#2dd4bf]' : 'hover:bg-[#334155] text-[#94a3b8] hover:text-white'}`}
            >
              <Sparkles className="w-4 h-4" />
            </button>
            <button 
              id="btn-reset-cam"
              onClick={resetView} 
              title="Reset Viewport"
              className="px-2 py-1 bg-[#334155] hover:bg-[#475569] text-[10px] font-bold rounded text-white cursor-pointer"
            >
              Reset
            </button>
          </div>

          {/* THE 3D CANVAS */}
          <div className="flex-1 w-full relative min-h-[400px]">
            <canvas
              id="3d-projection-canvas"
              ref={canvasRef}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
              onClick={handleCanvasClick}
              onTouchStart={handleTouchStart}
              onTouchMove={handleTouchMove}
              onTouchEnd={handleMouseUp}
              className="w-full h-full cursor-grab active:cursor-grabbing block"
            />

            {/* Hover tooltip overlay */}
            {hoveredBox && (
              <div 
                id="canvas-tooltip"
                className="absolute pointer-events-none bg-[#0f172a]/95 border border-[#334155] p-2.5 rounded shadow-xl text-xs space-y-1 z-20 max-w-[240px]"
                style={{
                  bottom: '16px',
                  left: '16px',
                }}
              >
                <div className="flex items-center justify-between gap-1.5 border-b border-[#334155] pb-1">
                  <span className="font-mono font-bold text-[#2dd4bf]">{hoveredBox.Box_ID}</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded uppercase font-bold bg-[#1e293b] text-white">
                    Layer {hoveredBox.Layer_ID}
                  </span>
                </div>
                <p className="text-[11px] text-white line-clamp-1">{hoveredBox.material_number}</p>
                <div className="grid grid-cols-2 gap-x-2 text-[10px] text-[#94a3b8]">
                  <span>Family: <strong className="text-white">{hoveredBox.family}</strong></span>
                  <span>Weight: <strong className="text-white">{hoveredBox.weight} kg</strong></span>
                  <span className="col-span-2 mt-0.5">Dims: <strong className="text-white">{Math.abs(hoveredBox.x_max - hoveredBox.x_min)}x{Math.abs(hoveredBox.y_max - hoveredBox.y_min)}x{Math.abs(hoveredBox.z_max - hoveredBox.z_min)} cm</strong></span>
                </div>
              </div>
            )}
          </div>

          {/* Color palette / Legend footer bar */}
          <footer className="bg-[#1e293b]/70 border-t border-[#334155]/80 p-4 shrink-0">
            <span className="text-[9px] font-bold text-[#2dd4bf] uppercase tracking-widest block mb-2">Heuristic Class Palette Legend</span>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {Object.entries(FAMILY_COLORS).map(([name, schema]) => {
                if (name === 'UNKNOWN') return null;
                const count = processedBoxes.filter(b => b.family === name && b.status !== 'FAILED').length;
                const failCount = processedBoxes.filter(b => b.status === 'FAILED').length;
                const displayCount = name === 'FAILED' ? failCount : count;
                
                if (displayCount === 0) return null;
                
                return (
                  <div key={name} className="flex items-center gap-2 text-xs bg-[#0f172a]/60 px-2.5 py-1.5 rounded border border-[#334155]/60 hover:border-[#2dd4bf]/40 transition-colors shadow-sm">
                    <span 
                      className="w-3.5 h-3.5 rounded-sm border block shadow-inner"
                      style={{
                        backgroundColor: schema.fill,
                        borderColor: schema.stroke
                      }}
                    />
                    <span className="text-[#cbd5e1] font-medium">{schema.label || name}</span>
                    <span className="text-[10px] font-mono font-bold text-[#2dd4bf]">({displayCount})</span>
                  </div>
                );
              })}
            </div>
          </footer>

        </main>

        {/* ================================== RIGHT PANEL: SAFETY ALERTS & INSPECTOR (3 columns) ================================== */}
        <aside id="right-sidebar-diagnostics" className="lg:col-span-3 bg-[#1e293b] p-5 flex flex-col gap-6 overflow-y-auto">
          
          {/* Active Box Physics Inspector */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-[#2dd4bf] uppercase tracking-widest border-b border-[#334155] pb-1.5 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5" /> Physics Inspector
            </h3>

            {selectedBox ? (
              <div id="inspector-card" className="bg-[#0f172a] border border-[#334155] rounded-lg p-4 space-y-3.5">
                
                <div className="flex items-center justify-between border-b border-[#334155] pb-2">
                  <div className="flex flex-col">
                    <span className="text-[9px] text-[#94a3b8] uppercase font-bold tracking-wider">Selected Case ID</span>
                    <span className="font-mono text-sm font-bold text-[#2dd4bf]">{selectedBox.Box_ID}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    selectedBox.status === 'FAILED' 
                      ? 'bg-[#ef4444]/15 border border-[#ef4444]/30 text-[#f87171]' 
                      : 'bg-[#10b981]/15 border border-[#10b981]/30 text-[#34d399]'
                  }`}>
                    {selectedBox.status}
                  </span>
                </div>

                {/* Main Details */}
                <div className="space-y-2 text-xs">
                  <div>
                    <span className="text-[#94a3b8] block text-[10px] uppercase font-semibold">Material / Product Description</span>
                    <span className="text-[#cbd5e1] font-medium block mt-0.5">{selectedBox.material_number}</span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 pt-1">
                    <div>
                      <span className="text-[#94a3b8] block text-[10px] uppercase font-semibold">Family Class</span>
                      <span className="text-[#cbd5e1] font-mono font-bold mt-0.5 block">{selectedBox.family}</span>
                    </div>
                    <div>
                      <span className="text-[#94a3b8] block text-[10px] uppercase font-semibold">Net Weight</span>
                      <span className="text-[#cbd5e1] font-bold mt-0.5 block">{selectedBox.weight} kg</span>
                    </div>
                  </div>

                  <div className="border-t border-[#334155] pt-2 mt-2 space-y-1.5">
                    <span className="text-[#94a3b8] block text-[10px] uppercase font-semibold">3D Spatial Extents (cm)</span>
                    <div className="grid grid-cols-3 gap-1.5 text-center text-[10.5px]">
                      <div className="bg-[#1e293b] p-1 rounded border border-[#334155]/60">
                        <span className="text-[#94a3b8] block text-[9px] font-bold">X (Length)</span>
                        <span className="font-mono text-[#cbd5e1]">{selectedBox.x_min} - {selectedBox.x_max}</span>
                      </div>
                      <div className="bg-[#1e293b] p-1 rounded border border-[#334155]/60">
                        <span className="text-[#94a3b8] block text-[9px] font-bold">Y (Width)</span>
                        <span className="font-mono text-[#cbd5e1]">{selectedBox.y_min} - {selectedBox.y_max}</span>
                      </div>
                      <div className="bg-[#1e293b] p-1 rounded border border-[#334155]/60">
                        <span className="text-[#94a3b8] block text-[9px] font-bold">Z (Height)</span>
                        <span className="font-mono text-[#cbd5e1]">{selectedBox.z_min} - {selectedBox.z_max}</span>
                      </div>
                    </div>
                  </div>

                  <div className="bg-[#1e293b]/50 p-2.5 rounded-lg border border-[#334155] text-[11px] space-y-1 mt-2">
                    <span className="text-[#2dd4bf] font-bold block">Support Diagnostics</span>
                    {selectedBox.z_min === minZOfActivePallet ? (
                      <p className="text-[#34d399] flex items-center gap-1">✓ Placed directly on the wood base.</p>
                    ) : selectedBox.isFloating ? (
                      <p className="text-[#fbbf24] flex items-center gap-1">⚠️ Lack of support base! Critical floating check failure.</p>
                    ) : (
                      <p className="text-[#34d399] flex items-center gap-1">✓ Interlocking supports verified underneath.</p>
                    )}
                  </div>
                </div>

                <button 
                  id="btn-deselect-box"
                  onClick={() => setSelectedBox(null)}
                  className="w-full py-1 bg-[#334155] hover:bg-[#475569] border border-[#475569] rounded text-[11px] font-bold text-white transition cursor-pointer"
                >
                  Clear Selection
                </button>

              </div>
            ) : (
              <div id="inspector-placeholder" className="bg-[#0f172a] border border-[#334155] border-dashed rounded-lg p-6 text-center text-xs text-[#94a3b8] space-y-2">
                <HelpCircle className="w-8 h-8 mx-auto text-[#475569]" />
                <p className="font-medium text-[#cbd5e1]">No Case Selected</p>
                <p className="text-[10.5px]">Click any box in the 3D projection viewport to lock its stability diagnostics and spatial bounds.</p>
              </div>
            )}
          </div>

          {/* Live Heuristics Warnings Alert Center */}
          <div className="flex-1 flex flex-col space-y-3 min-h-[220px]">
            <h3 className="text-xs font-bold text-[#e41e2b] uppercase tracking-widest border-b border-[#334155] pb-1.5 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" /> Stability Warnings Center
            </h3>

            {warningsList.length > 0 ? (
              <div id="warnings-list" className="space-y-2 flex-1 overflow-y-auto max-h-[380px] pr-1">
                {warningsList.map((warn) => (
                  <div 
                    id={warn.id}
                    key={warn.id}
                    onClick={() => {
                      setSelectedBox(warn.boxRef);
                      // Move camera slightly toward that area for satisfying UX
                      setAutoRotate(false);
                      setYaw(Math.atan2(
                        (warn.boxRef.y_min + warn.boxRef.y_max)/2 - PALLET_DEPTH/2,
                        (warn.boxRef.x_min + warn.boxRef.x_max)/2 - PALLET_WIDTH/2
                      ));
                    }}
                    className={`p-2.5 rounded-lg border text-[11px] leading-snug cursor-pointer transition-all hover:translate-x-1 ${
                      warn.type === 'failed' || warn.type === 'ceiling'
                        ? 'bg-[#ef4444]/5 border-[#ef4444]/30 hover:bg-[#ef4444]/10 text-white'
                        : 'bg-[#fbbf24]/5 border-[#fbbf24]/30 hover:bg-[#fbbf24]/10 text-white'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 font-bold mb-1">
                      <AlertTriangle className={`w-3.5 h-3.5 ${warn.type === 'failed' || warn.type === 'ceiling' ? 'text-[#ef4444]' : 'text-[#fbbf24]'}`} />
                      <span className="font-mono text-[#cbd5e1]">{warn.boxId}</span>
                    </div>
                    <p className="text-[#94a3b8]">{warn.message}</p>
                    <span className="text-[9px] text-[#2dd4bf] mt-1 block font-semibold hover:underline">Click to center view →</span>
                  </div>
                ))}
              </div>
            ) : (
              <div id="warnings-placeholder" className="bg-[#10b981]/5 border border-[#10b981]/20 rounded-lg p-5 text-center text-xs text-[#94a3b8] space-y-1.5 flex-1 flex flex-col justify-center">
                <CheckCircle2 className="w-8 h-8 mx-auto text-[#10b981]" />
                <p className="font-bold text-[#cbd5e1] text-[11px]">Perfect Heuristic Validation!</p>
                <p className="text-[10px]">No footprint overhangs, Door clear heights validated, and direct gravity bases confirmed for all models.</p>
              </div>
            )}
          </div>

        </aside>

      </div>

    </div>
  );
}
