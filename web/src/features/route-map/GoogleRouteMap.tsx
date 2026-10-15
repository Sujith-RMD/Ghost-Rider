import { useEffect, useState } from "react";
import { APIProvider, Map, useMap } from "@vis.gl/react-google-maps";
import { Minus, Plus, LocateFixed } from "lucide-react";
import type { Session } from "../../api/display";
import { numeric } from "../../lib/metric";
import { useSelection } from "../../app/store";
export function binStyle(sampled: boolean, condition: string) {
  return !sampled
    ? { color: "#E8E4D3", opacity: 0.22, dashed: true }
    : condition === "good"
      ? { color: "#00AEBB", opacity: 1, dashed: false }
      : condition === "bad"
        ? { color: "#E5694F", opacity: 1, dashed: false }
        : condition === "review"
          ? { color: "#E3B04B", opacity: 1, dashed: true }
          : { color: "#E8E4D3", opacity: 0.48, dashed: true };
}
function MapLayers({ session }: { session: Session }) {
  const map = useMap();
  const { layers, selectBin, binId } = useSelection();
  useEffect(() => {
    if (!map) return;
    const overlays: (
      google.maps.Polyline | google.maps.Circle | google.maps.Marker
    )[] = [];
    const bounds = new google.maps.LatLngBounds();
    const listeners: google.maps.MapsEventListener[] = [];
    for (const b of session.bins) {
      if (!b.geometry?.length) continue;
      b.geometry.forEach((p) => bounds.extend(p));
      if (layers.bins) {
        const style = binStyle(
          b.sampled,
          numeric(b.median) === undefined ? "unknown" : b.condition,
        );
        const line = new google.maps.Polyline({
          map,
          path: b.geometry,
          strokeColor: style.color,
          strokeOpacity: style.dashed ? 0 : style.opacity,
          strokeWeight: b.id === binId ? 9 : b.sampled ? 6 : 2,
          icons: style.dashed
            ? [
                {
                  icon: {
                    path: "M 0,-1 0,1",
                    strokeOpacity: style.opacity,
                    scale: 2,
                  },
                  offset: "0",
                  repeat: "12px",
                },
              ]
            : undefined,
        });
        overlays.push(line);
        if (b.sampled)
          listeners.push(line.addListener("click", () => selectBin(b.id)));
      }
      if (b.severe) {
        overlays.push(
          new google.maps.Marker({
            map,
            position: b.geometry[0],
            title: "Inspect: possible severe observed defect",
            icon: {
              path: "M 0,-7 7,0 0,7 -7,0 Z",
              fillOpacity: 0,
              strokeColor: "#E5694F",
              strokeWeight: 2,
              scale: 1,
            },
          }),
        );
      }
    }
    // Raw GPS points and accuracy circles require actual per-point backend records.
    // Do not substitute bin vertices for those independent observations.
    if (!bounds.isEmpty()) map.fitBounds(bounds, 70);
    return () => {
      listeners.forEach((l) => l.remove());
      overlays.forEach((o) => o.setMap(null));
    };
  }, [map, session, layers, selectBin, binId]);
  return (
    <div className="map-controls glass-card">
      <button
        aria-label="Zoom in"
        onClick={() => map?.setZoom((map.getZoom() ?? 14) + 1)}
      >
        <Plus />
      </button>
      <button
        aria-label="Fit sampled route"
        onClick={() => {
          const bounds = new google.maps.LatLngBounds();
          session.bins.forEach((b) =>
            b.geometry?.forEach((p) => bounds.extend(p)),
          );
          if (!bounds.isEmpty()) map?.fitBounds(bounds, 70);
        }}
      >
        <LocateFixed />
      </button>
      <button
        aria-label="Zoom out"
        onClick={() => map?.setZoom((map.getZoom() ?? 14) - 1)}
      >
        <Minus />
      </button>
    </div>
  );
}
function SelectedMapAnchor({
  session,
  onAnchor,
}: {
  session: Session;
  onAnchor?: (point: { x: number; y: number } | null) => void;
}) {
  const map = useMap();
  const selected = useSelection((s) => s.binId);
  useEffect(() => {
    if (!map || !onAnchor) return;
    const bin = session.bins.find((b) => b.id === selected);
    const point = bin?.geometry?.[Math.floor((bin.geometry?.length ?? 0) / 2)];
    if (!point) {
      onAnchor(null);
      return;
    }
    const overlay = new google.maps.OverlayView();
    overlay.onAdd = () => {};
    overlay.onRemove = () => {};
    overlay.draw = () => {
      const pixel = overlay
        .getProjection()
        ?.fromLatLngToContainerPixel(new google.maps.LatLng(point));
      if (pixel) onAnchor({ x: pixel.x, y: pixel.y });
    };
    overlay.setMap(map);
    return () => overlay.setMap(null);
  }, [map, session, selected, onAnchor]);
  return null;
}
export default function GoogleRouteMap({
  session,
  onUnavailable,
  onAnchor,
}: {
  session: Session;
  onUnavailable?: (reason: string) => void;
  onAnchor?: (point: { x: number; y: number } | null) => void;
}) {
  const [failure, setFailure] = useState<string | null>(null);
  const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined;
  useEffect(() => {
    const w = window as Window & { gm_authFailure?: () => void };
    const previous = w.gm_authFailure;
    w.gm_authFailure = () => setFailure("auth_or_billing");
    return () => {
      w.gm_authFailure = previous;
    };
  }, []);
  useEffect(() => {
    if (failure) onUnavailable?.(failure);
  }, [failure, onUnavailable]);
  const first = session.bins.find((b) => b.geometry?.length)?.geometry?.[0];
  if (!session.hasGps || !first || !key || failure) return null;
  return (
    <div className="google-map" aria-label="Sampled strip on Google Maps">
      <APIProvider apiKey={key} onError={() => setFailure("network")}>
        <Map
          defaultCenter={first}
          defaultZoom={16}
          disableDefaultUI
          styles={[
            { elementType: "geometry", stylers: [{ color: "#0C1A19" }] },
            {
              elementType: "labels.text.fill",
              stylers: [{ color: "#E8E4D3" }],
            },
            {
              elementType: "labels.text.stroke",
              stylers: [{ color: "#031211" }],
            },
            { featureType: "poi", stylers: [{ visibility: "off" }] },
            { featureType: "transit", stylers: [{ visibility: "off" }] },
            { featureType: "water", stylers: [{ color: "#031211" }] },
            {
              featureType: "road",
              elementType: "geometry",
              stylers: [{ color: "#1F2B28" }],
            },
          ]}
        >
          <MapLayers session={session} />
          <SelectedMapAnchor session={session} onAnchor={onAnchor} />
        </Map>
      </APIProvider>
      {session.simulated && (
        <span className="simulated-route chip">Simulated route</span>
      )}
      <span className="map-area-note">
        Sampled strip only / coverage{" "}
        <span>{numeric(session.coverage) ?? "unknown"}%</span>
      </span>
    </div>
  );
}
