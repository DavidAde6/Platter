import { useRef, useState } from "react";
import { Camera } from "lucide-react";
import { uploadMealImage, type MealUploadMetadata } from "../lib/mealLog";

export function Scan() {
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<MealUploadMetadata | null>(null);
  const [mealId, setMealId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleClickUpload = () => {
    fileInputRef.current?.click();
  };

  const uploadFile = async (file: File, imageDataUrl: string) => {
    try {
      setLoading(true);
      setErrorMsg(null);
      setUploadResult(null);
      setMealId(null);

      const data = await uploadMealImage(file);
      setUploadResult(data.metadata);
      setMealId(data.meal_id);
      // The server now returns auth-protected proxy paths rather than public
      // URLs, so reuse the locally-read image for the preview.
      setPreviewUrl(imageDataUrl);
    } catch (err) {
      console.error(err);
      setErrorMsg(
        err instanceof Error ? err.message : "Could not analyze this image. Please try another one.",
      );
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
            Upload a photo to save it to your meal log. Nutrition analysis is coming next.
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
              <div className="upload-helper">Supports JPG, PNG, WEBP, HEIC</div>
            </>
          )}
          {hasImage && previewUrl && (
            <div
              className="upload-area-image"
              style={{ backgroundImage: `url(${previewUrl})` }}
            >
              <div className="upload-area-overlay">
                <span className="upload-area-overlay-text">
                  {loading ? "Uploading…" : "Uploaded"}
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

        {uploadResult && (
          <section className="scan-result-card">
            <div className="scan-result-header">
              <div>
                <h2 className="scan-result-title">Upload saved</h2>
                <p className="scan-result-food">
                  {uploadResult.filename ?? "Meal image"} · Meal #{mealId}
                </p>
              </div>
              <span className="scan-result-serving">Metadata extracted</span>
            </div>
            <div className="scan-result-grid">
              <div className="scan-result-metric">
                <span>Format</span>
                <strong>{uploadResult.image_format ?? "—"}</strong>
              </div>
              <div className="scan-result-metric">
                <span>Size</span>
                <strong>
                  {uploadResult.width && uploadResult.height
                    ? `${uploadResult.width}×${uploadResult.height}`
                    : "—"}
                </strong>
              </div>
              <div className="scan-result-metric">
                <span>File size</span>
                <strong>
                  {uploadResult.file_size_bytes
                    ? `${Math.round(uploadResult.file_size_bytes / 1024)} KB`
                    : "—"}
                </strong>
              </div>
              <div className="scan-result-metric">
                <span>Camera</span>
                <strong>
                  {[uploadResult.make, uploadResult.model].filter(Boolean).join(" ") || "—"}
                </strong>
              </div>
            </div>
          </section>
        )}

        <div className="scan-benefits">
          <div className="scan-benefit-card">
            Saved to your account — visible in Meal Log
          </div>
          <div className="scan-benefit-card">
            EXIF metadata stored for future analysis
          </div>
          <div className="scan-benefit-card">
            Nutrition breakdown coming in a future update
          </div>
        </div>
      </section>
    </div>
  );
}
