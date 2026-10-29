// Экокинеу: standalone C++ inference parity/latency probe, no Python inference.
// Input: contiguous float32 RGB NCHW tensor, shape 1x3xHxW from model input.
#include <openvino/openvino.hpp>
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <vector>
int main(int argc,char**argv){
 try{
  if(argc!=5){std::cerr<<"Usage: infer_openvino model.xml input.f32 output.f32 repeats\n";return 2;}
  int repeats=std::stoi(argv[4]);if(repeats<1||repeats>1000)throw std::runtime_error("Invalid repeat count");
  ov::Core core;auto model=core.compile_model(argv[1],"CPU",ov::inference_num_threads(2),ov::hint::performance_mode(ov::hint::PerformanceMode::LATENCY));
  auto req=model.create_infer_request();auto input=req.get_input_tensor();
  if(input.get_element_type()!=ov::element::f32)throw std::runtime_error("Need float32 model input");
  std::ifstream file(argv[2],std::ios::binary|std::ios::ate);
  if(!file||static_cast<size_t>(file.tellg())!=input.get_byte_size())throw std::runtime_error("Input tensor size mismatch");
  file.seekg(0);file.read(reinterpret_cast<char*>(input.data<float>()),input.get_byte_size());
  req.infer();std::vector<double>ms;
  for(int i=0;i<repeats;++i){auto start=std::chrono::steady_clock::now();req.infer();ms.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());}
  std::sort(ms.begin(),ms.end());auto output=req.get_output_tensor();
  if(output.get_element_type()!=ov::element::f32)throw std::runtime_error("Need float32 output");
  std::ofstream out(argv[3],std::ios::binary);out.write(reinterpret_cast<char*>(output.data<float>()),output.get_byte_size());
  std::cout<<"{\"backend\":\"standalone C++ OpenVINO CPU\",\"repeats\":"<<repeats<<",\"median_inference_ms\":"<<ms[ms.size()/2]<<",\"output_floats\":"<<output.get_size()<<"}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
