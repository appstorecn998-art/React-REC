import {defineConfig} from 'vite';
export default defineConfig({server:{host:'127.0.0.1',port:8767,strictPort:true,proxy:{'/api':'http://127.0.0.1:8771'}},build:{target:'es2022'}});
