import { routeHandlers } from "../../../server/backendProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const handle = routeHandlers("/uploads");
export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
