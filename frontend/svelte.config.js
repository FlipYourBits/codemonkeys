import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({
      pages: '../codemonkeys/dashboard/static',
      assets: '../codemonkeys/dashboard/static',
      fallback: 'index.html',
    }),
  },
};
