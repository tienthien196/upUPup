#include <iostream>
using namespace std;


struct Node {
    int data;
    Node* next;
};

Node* TimKiem(Node* head, int x) {
    Node* p = head;
    while (p != NULL) {
        if (p->data == x) {
            return p;
        }
        p = p->next; 
    }
    return NULL; 
}   

int main() {
    // Tạo danh sách: 1 -> 3 -> 7 -> 9
    Node* head = new Node{1, nullptr};
    head->next = new Node{3, nullptr};
    head->next->next = new Node{7, nullptr};
    head->next->next->next = new Node{9, nullptr};

    Node* p = TimKiem(head, 7);
    if (p == NULL)
        cout << "Khong tim thay";
    else
        cout << p->data; // In ra: 7


    return 0;
}