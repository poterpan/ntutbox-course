// @ntutbox/map 0.9 還沒附型別；這裡只宣告教室地圖（components/rooms/map）用到的部分。
// 套件附上型別後刪掉這個檔案。
declare module "@ntutbox/map" {
  export type MapView = "campus" | "overview" | "floor";
  export type MapRoomStatus = "free" | "soon" | "busy" | "unknown";

  export interface BuildingConfig {
    name: string;
    short: string;
    entranceBearing: number;
    entranceConfirmed?: boolean;
  }

  export interface CampusSource {
    frame: string;
    load(): Promise<{
      buildings: Record<string, BuildingConfig>;
      current: { revision: number; update_sequence: number | null };
    }>;
  }

  export function campusCdnSource(baseUrl?: string): CampusSource;

  export interface FloorStats {
    id: string;
    total: number;
    available: number;
    free: number;
  }

  export interface ViewInfo {
    view: MapView;
    building: string;
    buildingName?: string;
    buildingShort?: string;
    floor: string | null;
    floors: FloorStats[];
  }

  export interface SelectedRoom<O = unknown> {
    key: string;
    buildingId: string;
    buildingName: string;
    floorId: string;
    classNumber: string;
    gisName: string;
    status: MapRoomStatus;
    occupancy: O | null;
  }

  export interface MapError {
    type: "load-failed" | "building-load-failed" | "floor-missing";
    building?: string;
    floor?: string;
    error?: unknown;
  }

  export interface IndoorMapOptions<O extends { status: MapRoomStatus }> {
    source?: CampusSource;
    buildings?: Record<string, BuildingConfig>;
    occupancy?: Map<string, O>;
    initialBuilding?: string;
    initialView?: MapView;
    preload?: string[];
    getInsets?: () => { top?: number; right?: number; bottom?: number; left?: number };
    onViewChange?: (info: ViewInfo) => void;
    onRoomSelect?: (room: SelectedRoom<O> | null) => void;
    onCampusFocus?: (focus: { buildingId: string; name: string; via: string } | null) => void;
    onError?: (error: MapError) => void;
    onLoading?: (info: { building: string }) => void;
    onNotice?: (text: string) => void;
  }

  export interface IndoorMap<O> {
    ready: Promise<void>;
    setView(target: { building?: string; view?: MapView; floor?: string | null; animate?: boolean }): Promise<boolean>;
    selectRoom(key: string, options?: { animate?: boolean }): Promise<boolean>;
    setOccupancy(map: Map<string, O>): void;
    enterBuilding(id: string): void;
    resetView(): void;
    clearSelection(): void;
    getView(): ViewInfo;
    destroy(): void;
  }

  export function createIndoorMap<O extends { status: MapRoomStatus }>(
    container: HTMLElement,
    options?: IndoorMapOptions<O>,
  ): IndoorMap<O>;

  export function floorRank(id: string): number;
}

declare module "@ntutbox/map/style.css";
