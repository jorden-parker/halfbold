import index from "./index.html";

const server = Bun.serve({
  hostname: "127.0.0.1",
  port: 1420,
  routes: { "/*": index },
  development: { hmr: true, console: true },
});

console.log(`halfbold dev server on ${server.url}`);
