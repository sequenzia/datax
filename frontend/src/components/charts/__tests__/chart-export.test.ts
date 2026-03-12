import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { exportChart } from "../chart-export";

// Mock plotly.js
const mockDownloadImage = vi.fn().mockResolvedValue(undefined);
const mockToImage = vi.fn().mockResolvedValue("data:image/svg+xml;base64,abc123");

vi.mock("plotly.js", () => ({
  default: {
    downloadImage: (...args: unknown[]) => mockDownloadImage(...args),
    toImage: (...args: unknown[]) => mockToImage(...args),
  },
  downloadImage: (...args: unknown[]) => mockDownloadImage(...args),
  toImage: (...args: unknown[]) => mockToImage(...args),
}));

describe("chart-export", () => {
  let originalCreateElement: typeof document.createElement;
  let mockLink: {
    href: string;
    download: string;
    click: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    mockDownloadImage.mockClear();
    mockToImage.mockClear();
    mockLink = { href: "", download: "", click: vi.fn() };

    // Save original before mocking
    originalCreateElement = document.createElement.bind(document);

    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") return mockLink as unknown as HTMLAnchorElement;
      return originalCreateElement(tag);
    });
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => node);
    vi.spyOn(document.body, "removeChild").mockImplementation((node) => node);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("exportChart", () => {
    it("calls Plotly.downloadImage for PNG format with 2x retina scale", async () => {
      const fakeDiv = originalCreateElement("div");

      await exportChart(fakeDiv, {
        format: "png",
        filename: "test_chart",
      });

      expect(mockDownloadImage).toHaveBeenCalledTimes(1);
      expect(mockDownloadImage).toHaveBeenCalledWith(fakeDiv, {
        format: "png",
        filename: "test_chart",
        width: 1200,
        height: 600,
        scale: 2,
      });
    });

    it("calls Plotly.toImage for SVG format and triggers download", async () => {
      const fakeDiv = originalCreateElement("div");

      await exportChart(fakeDiv, {
        format: "svg",
        filename: "test_chart",
      });

      expect(mockToImage).toHaveBeenCalledTimes(1);
      expect(mockToImage).toHaveBeenCalledWith(fakeDiv, {
        format: "svg",
        width: 1200,
        height: 600,
        scale: 1,
      });

      expect(mockLink.download).toBe("test_chart.svg");
      expect(mockLink.click).toHaveBeenCalledTimes(1);
    });

    it("uses custom width and height when provided", async () => {
      const fakeDiv = originalCreateElement("div");

      await exportChart(fakeDiv, {
        format: "png",
        filename: "custom_size",
        width: 800,
        height: 400,
        scale: 3,
      });

      expect(mockDownloadImage).toHaveBeenCalledWith(fakeDiv, {
        format: "png",
        filename: "custom_size",
        width: 800,
        height: 400,
        scale: 3,
      });
    });

    it("uses default filename when not provided", async () => {
      const fakeDiv = originalCreateElement("div");

      await exportChart(fakeDiv, { format: "png" });

      expect(mockDownloadImage).toHaveBeenCalledWith(
        fakeDiv,
        expect.objectContaining({ filename: "chart" }),
      );
    });

    it("propagates errors from Plotly.downloadImage", async () => {
      mockDownloadImage.mockRejectedValueOnce(new Error("Download failed"));
      const fakeDiv = originalCreateElement("div");

      await expect(
        exportChart(fakeDiv, { format: "png" }),
      ).rejects.toThrow("Download failed");
    });

    it("propagates errors from Plotly.toImage", async () => {
      mockToImage.mockRejectedValueOnce(new Error("Conversion failed"));
      const fakeDiv = originalCreateElement("div");

      await expect(
        exportChart(fakeDiv, { format: "svg" }),
      ).rejects.toThrow("Conversion failed");
    });
  });
});
