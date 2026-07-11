module.exports = {
  apps: [
    {
      name: "wa-adapter",
      script: "src/index.js",
      cwd: __dirname,
      restart_delay: 3000,
      max_restarts: 50,
      time: true,
    },
  ],
};
