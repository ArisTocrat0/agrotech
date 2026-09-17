#include <algorithm>
#include <cstddef>
// Inputs are in stable descending score order. Labels encode species + stage.
extern "C" int agro_nms(const double* boxes, const int* groups, int n,
                         double threshold, int* output) {
    int kept = 0;
    for (int i = 0; i < n; ++i) {
        const double* a = boxes + static_cast<std::size_t>(i) * 4;
        const double a_area = (a[2]-a[0])*(a[3]-a[1]);
        bool suppress = false;
        for (int k = 0; k < kept; ++k) {
            int j = output[k];
            if (groups[i] != groups[j]) continue;
            const double* b = boxes + static_cast<std::size_t>(j) * 4;
            double w = std::max(0.0, std::min(a[2], b[2]) - std::max(a[0], b[0]));
            double h = std::max(0.0, std::min(a[3], b[3]) - std::max(a[1], b[1]));
            double intersection = w * h;
            double area = a_area + (b[2]-b[0])*(b[3]-b[1]) - intersection;
            if (area > 0 && intersection / area > threshold) { suppress = true; break; }
        }
        if (!suppress) output[kept++] = i;
    }
    return kept;
}
