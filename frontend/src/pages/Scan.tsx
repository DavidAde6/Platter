import { useRef, useState } from "react";
import { Camera } from "lucide-react";
import { addMealLogItem } from "../lib/mealLog";
import type { ScanApiResponse } from "../lib/mealLog";

export function Scan() {
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<ScanApiResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleClickUpload = () => {
    fileInputRef.current?.click();
  };

  const uploadFile = async (file: File, imageDataUrl: string) => {
    const formData = new FormData();
    formData.append("image", file);
    const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

    try {
      setLoading(true);
      setErrorMsg(null);

      const res = await fetch(`${apiBaseUrl}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Upload failed (${res.status})`);
      }

      const data: ScanApiResponse = await res.json();
      setScanResult(data);

      const energy = data.macros.Energy?.value ?? 0;
      const protein = data.macros.Protein?.value ?? 0;
      const carbs = data.macros.Carbohydrate?.value ?? 0;
      const fats = data.macros["Total Fat"]?.value ?? 0;

      addMealLogItem({
        id: crypto.randomUUID(),
        name: data.food,
        date: new Date().toLocaleDateString(),
        protein: `${Math.round(protein)}g`,
        carbs: `${Math.round(carbs)}g`,
        fats: `${Math.round(fats)}g`,
        calories: Math.round(energy),
        image: imageDataUrl,
      });
      console.log("Server:", data);
    } catch (err) {
      console.error(err);
      setErrorMsg("Could not analyze this image. Please try another one.");
    } finally {
      setLoading(false);
    }
  };

  const fileToDataUrl = (file: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => reject(new Error("Failed to read image"));
      reader.readAsDataURL(file);
    });

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;

    const imageDataUrl = await fileToDataUrl(selectedFile);
    setPreviewUrl(imageDataUrl);

    uploadFile(selectedFile, imageDataUrl);
  };

  const hasImage = Boolean(previewUrl);

  return (
    <div className="page">
      <section className="page-card">
        <header className="page-card-header">
          <h1 className="page-card-title">Snap your meal</h1>
          <p className="page-card-subtitle">
            Our AI will identify ingredients and calculate nutrition instantly.
          </p>
        </header>

        <button
          type="button"
          className={`upload-area ${hasImage ? "upload-area--with-image" : ""}`}
          onClick={handleClickUpload}
        >
          {!hasImage && (
            <>
              <div className="upload-icon-wrapper">
                <Camera className="upload-icon" />
              </div>
              <div className="upload-title">
                Click to upload or take a photo
              </div>
              <div className="upload-helper">Supports JPG, PNG</div>
            </>
          )}
          {hasImage && previewUrl && (
            <div
              className="upload-area-image"
              style={{ backgroundImage: `url(${previewUrl})` }}
            >
              <div className="upload-area-overlay">
                <span className="upload-area-overlay-text">
                  {loading ? "Loading…" : "Uploaded"}
                </span>
              </div>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="upload-input-hidden"
            onChange={handleFileChange}
          />
        </button>

        {errorMsg && <p className="scan-error">{errorMsg}</p>}

        {scanResult && (
          <section className="scan-result-card">
            <div className="scan-result-header">
              <div>
                <h2 className="scan-result-title">Nutrition result</h2>
                <p className="scan-result-food">{scanResult.food}</p>
              </div>
              <span className="scan-result-serving">
                Serving: {Math.round(scanResult.serving)} g
              </span>
            </div>
            <div className="scan-result-grid">
              <div className="scan-result-metric">
                <span>Calories</span>
                <strong>{Math.round(scanResult.macros.Energy?.value ?? 0)} kcal</strong>
              </div>
              <div className="scan-result-metric">
                <span>Protein</span>
                <strong>{Math.round(scanResult.macros.Protein?.value ?? 0)} g</strong>
              </div>
              <div className="scan-result-metric">
                <span>Carbs</span>
                <strong>{Math.round(scanResult.macros.Carbohydrate?.value ?? 0)} g</strong>
              </div>
              <div className="scan-result-metric">
                <span>Fat</span>
                <strong>{Math.round(scanResult.macros["Total Fat"]?.value ?? 0)} g</strong>
              </div>
            </div>
          </section>
        )}

        <div className="scan-benefits">
          <div className="scan-benefit-card">
            Industry standard level accuracy in ingredient detection
          </div>
          <div className="scan-benefit-card">
            Instant macro breakdown for every scan
          </div>
          <div className="scan-benefit-card">
            Personalized dietary tips tailored to your goals
          </div>
        </div>
      </section>
    </div>
  );
}
