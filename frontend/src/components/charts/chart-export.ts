export interface ExportOptions {
  format: "png" | "svg";
  filename?: string;
  width?: number;
  height?: number;
  scale?: number;
}

const DEFAULT_EXPORT_WIDTH = 1200;
const DEFAULT_EXPORT_HEIGHT = 600;

/**
 * Export a Plotly chart element as PNG or SVG.
 * Uses Plotly.downloadImage() for PNG (raster) and Plotly.toImage() + manual
 * download for SVG (vector). Retina resolution (2x) by default for PNG.
 *
 * Plotly is imported dynamically to avoid loading the full library at module
 * level, which would break test files that mock react-plotly.js but not plotly.js.
 */
export async function exportChart(
  graphDiv: HTMLElement,
  options: ExportOptions,
): Promise<void> {
  const Plotly = await import("plotly.js");

  const {
    format,
    filename = "chart",
    width = DEFAULT_EXPORT_WIDTH,
    height = DEFAULT_EXPORT_HEIGHT,
    scale = format === "png" ? 2 : 1,
  } = options;

  if (format === "png") {
    await Plotly.downloadImage(graphDiv as Plotly.PlotlyHTMLElement, {
      format: "png",
      filename,
      width,
      height,
      scale,
    });
  } else {
    const dataUrl = await Plotly.toImage(graphDiv as Plotly.PlotlyHTMLElement, {
      format: "svg",
      width,
      height,
      scale,
    });
    downloadDataUrl(dataUrl, `${filename}.svg`);
  }
}

/**
 * Export a KPI card DOM element as a PNG image using canvas.
 * Renders the element to a canvas via html-to-image-style approach using SVG
 * foreignObject, then triggers download.
 */
export async function exportKpiCard(
  element: HTMLElement,
  filename = "kpi-card",
): Promise<void> {
  const canvas = await elementToCanvas(element, 2);
  const dataUrl = canvas.toDataURL("image/png");
  downloadDataUrl(dataUrl, `${filename}.png`);
}

function downloadDataUrl(dataUrl: string, filename: string): void {
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

/**
 * Render an HTML element to a canvas using SVG foreignObject.
 * This approach avoids external dependencies and works for styled elements.
 */
async function elementToCanvas(
  element: HTMLElement,
  scale: number,
): Promise<HTMLCanvasElement> {
  const rect = element.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;

  const clone = element.cloneNode(true) as HTMLElement;
  const computedStyles = window.getComputedStyle(element);

  clone.style.backgroundColor =
    computedStyles.backgroundColor === "rgba(0, 0, 0, 0)"
      ? "#ffffff"
      : computedStyles.backgroundColor;
  clone.style.color = computedStyles.color;
  clone.style.padding = computedStyles.padding;
  clone.style.width = `${width}px`;
  clone.style.height = `${height}px`;

  const svgData = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
      <foreignObject width="100%" height="100%">
        <div xmlns="http://www.w3.org/1999/xhtml">
          ${clone.outerHTML}
        </div>
      </foreignObject>
    </svg>
  `;

  const svgBlob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);

  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    URL.revokeObjectURL(url);
    throw new Error("Failed to create canvas context");
  }

  ctx.scale(scale, scale);

  return new Promise<HTMLCanvasElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      resolve(canvas);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Failed to render KPI card to image"));
    };
    img.src = url;
  });
}
